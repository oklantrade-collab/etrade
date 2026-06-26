"""
eTrade v5.0 — EREP (Escalation / Recovery Strategy) Mechanism
============================================================

Este módulo gestiona la estrategia de Escalamiento EREP para posiciones en negativo.
Evita el cierre inmediato en pérdida y busca una salida en breakeven o con ganancia mínima
utilizando compras de refuerzo inteligentes (P2) basadas en bandas de Fibonacci o factores de escala.
"""

import asyncio
import time
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from app.core.logger import log_info, log_error, log_warning

# ── EREP CONFIGURATION (PASO 1 & 2) ──
EREP_CONFIG = {
    'crypto_futures': {
        # ── User's new config keys ──
        'max_loss_pct_to_activate': 6.0,
        # Si pérdida > 6% → NO activar EREP
        'p2_size_factor':           1.0,
        # P2 = P1 × 1.0 (mismo tamaño)
        'timeout_cycles':           4,
        # máximo 4 ciclos de 15m = 1 hora
        'max_drop_4h_pct':          5.0,
        # Si el mercado cayó >5% en 4H → no EREP
        'rsi_oversold':             10,
        # RSI <= 10 → comprar P2
        'ema_period_fast':          3,
        # EMA rápida (EMA3)
        'ema_period_slow':          9,
        # EMA lenta (EMA9)
        'min_pips_recovery':        0,
        # cerrar si pnl >= 0 (ganancia o cero)

        # ── Previous config keys ──
        'rsi_oversold_long':        10,
        'rsi_overbought_short':     90,
        'p2_min_factor':            0.5,
        'p2_max_factor':            3.0,
        'round_to_decimals':        1,
        'timeout_cycles_phase2':    4,
        'timeout_cycles_phase3':    8,
        'target_band_pct':          0.95,
        'min_gain_to_close':        0.0,
        'ema_fast':                 3,
        'ema_slow':                 9,
    },
    'forex_futures': {
        'max_loss_pct_to_activate': 1.5,
        'p2_size_factor':           1.0,
        'timeout_cycles':           4,
        'max_drop_4h_pct':          2.0,
        'rsi_oversold':             15,
        'ema_period_fast':          3,
        'ema_period_slow':          9,
        'min_pips_recovery':        0,

        'rsi_oversold_long':        15,
        'rsi_overbought_short':     85,
        'p2_min_factor':            0.5,
        'p2_max_factor':            3.0,
        'round_to_decimals':        1,
        'timeout_cycles_phase2':    4,
        'timeout_cycles_phase3':    8,
        'target_band_pct':          0.95,
        'min_gain_to_close':        0.0,
        'ema_fast':                 3,
        'ema_slow':                 9,
    },
    'stocks_spot': {
        'max_loss_pct_to_activate': 8.0,
        'p2_size_factor':           1.0,
        'timeout_cycles':           6,
        'max_drop_4h_pct':          10.0,
        'rsi_oversold':             20,
        'ema_period_fast':          3,
        'ema_period_slow':          9,
        'min_pips_recovery':        0,

        'rsi_oversold_long':        20,
        'rsi_overbought_short':     80,
        'p2_min_factor':            2.0,  # Mínimo 2.0x
        'p2_max_factor':            3.0,  # Máximo 3.0x
        'round_to_decimals':        0,
        'timeout_cycles_phase2':    6,
        'timeout_cycles_phase3':    12,
        'target_band_pct':          0.95,
        'min_gain_to_close':        0.0,
        'ema_fast':                 3,
        'ema_slow':                 9,
        'stock_round_thresholds': [
            (10,   5),
            (100,  10),
            (1000, 100),
            (float('inf'), 1000),
        ],
    },
}

# ════════════════════════════════════════════
# MÓDULO 1 — CALCULAR EMAs
# ════════════════════════════════════════════

def get_ema_cross(
    df_15m:      pd.DataFrame,
    fast_period: int = 3,
    slow_period: int = 9,
) -> dict:
    """
    Calcula EMA3 y EMA9 en 15m y determina si EMA3 > EMA9 (momentum alcista).
    """
    if df_15m is None or len(df_15m) < slow_period:
        return {
            'ema_fast':  0.0,
            'ema_slow':  0.0,
            'is_fast_above': True, # Default non-blocking
            'valid':     False,
        }

    # Normalize columns if needed
    col = 'close'
    if 'close' not in df_15m.columns and 'c' in df_15m.columns:
        col = 'c'

    closes = pd.to_numeric(df_15m[col], errors='coerce').dropna()
    if len(closes) < slow_period:
        return {
            'ema_fast':  0.0,
            'ema_slow':  0.0,
            'is_fast_above': True,
            'valid':     False,
        }

    ema_fast = float(closes.ewm(span=fast_period, adjust=False).mean().iloc[-1])
    ema_slow = float(closes.ewm(span=slow_period, adjust=False).mean().iloc[-1])

    return {
        'ema_fast':      round(ema_fast, 6),
        'ema_slow':      round(ema_slow, 6),
        'is_fast_above': ema_fast > ema_slow,
        'diff':          round(ema_fast - ema_slow, 6),
        'valid':         True,
    }


# ════════════════════════════════════════════
# MÓDULO 2 — DETECTAR SEÑAL SIPV PARA P2
# ════════════════════════════════════════════

def detect_p2_entry_signal(
    df_15m:    pd.DataFrame,
    snap:      dict,
    side:      str,
    symbol:    str,
    market_type: str = 'crypto_futures',
    df_5m:     pd.DataFrame = None,
) -> dict:
    """
    Detecta la señal para comprar P2.
    Supports LONG, SHORT, and Stocks.
    """
    cfg   = EREP_CONFIG.get(market_type, {})
    rsi_oversold = int(cfg.get('rsi_oversold', 10))
    signals_found = []

    is_long = side.lower() in ('long', 'buy')

    # ── SEÑAL A: SIPV (vela del 15m) & Bollinger / Fibonacci extremas ──────────
    if df_15m is not None and len(df_15m) >= 2:
        # Asegurar cálculo de bandas de Bollinger si no están en el DataFrame
        if 'bb_lower' not in df_15m.columns or 'bb_upper' not in df_15m.columns:
            try:
                col_close = 'close' if 'close' in df_15m.columns else ('c' if 'c' in df_15m.columns else '')
                if col_close:
                    closes = pd.to_numeric(df_15m[col_close], errors='coerce').ffill()
                    # Cálculo nativo robusto con Pandas (evita el bug de fillna con method de la librería ta)
                    rolling_mean = closes.rolling(window=20).mean()
                    rolling_std = closes.rolling(window=20).std()
                    df_15m['bb_lower'] = rolling_mean - (2 * rolling_std)
                    df_15m['bb_upper'] = rolling_mean + (2 * rolling_std)
            except Exception as e:
                log_error('EREP_BOLLINGER', f"Error calculando Bollinger Bands locales: {e}")

        last_closed = df_15m.iloc[-2]
        o = float(last_closed.get('open',  last_closed.get('o', 0)))
        c = float(last_closed.get('close', last_closed.get('c', 0)))
        h = float(last_closed.get('high',  last_closed.get('h', 0)))
        l = float(last_closed.get('low',   last_closed.get('l', 0)))
        bb_lower = float(last_closed.get('bb_lower', 0))
        bb_upper = float(last_closed.get('bb_upper', 0))

        if h > l and o > 0:
            body     = c - o
            body_pct = abs(body) / (h - l)

            if is_long:
                if body > 0 and body_pct >= 0.30:
                    signals_found.append({
                        'type':     'sipv_buy',
                        'strength': body_pct,
                        'reason':   f'Vela BUY 15m: cuerpo {body_pct*100:.1f}%',
                    })
            else:
                if body < 0 and body_pct >= 0.30:
                    signals_found.append({
                        'type':     'sipv_sell',
                        'strength': body_pct,
                        'reason':   f'Vela SELL 15m: cuerpo {body_pct*100:.1f}%',
                    })

        # LONG: Cierre por debajo o igual a Soporte 5 (Fibonacci)
        if is_long:
            lower_5 = float(snap.get('lower_5', 0))
            if lower_5 > 0 and c <= lower_5:
                signals_found.append({
                    'type':     'fib_extreme_low_5',
                    'strength': 0.85,
                    'reason':   f'Cierre de vela 15m (${c:.4f}) ≤ lower_5 (${lower_5:.4f})',
                })
            
            # LONG: (open < bb_lower) AND (close < bb_lower) (Rompimiento Extremo Bollinger)
            if bb_lower > 0 and o < bb_lower and c < bb_lower:
                signals_found.append({
                    'type':     'bollinger_breakout_low',
                    'strength': 0.95,
                    'reason':   f'Vela 15m completamente bajo Bollinger: open (${o:.4f}) < BB_L (${bb_lower:.4f}) y close (${c:.4f}) < BB_L',
                })
        # SHORT: Cierre por encima o igual a Resistencia 5 (Fibonacci)
        else:
            upper_5 = float(snap.get('upper_5', 0))
            if upper_5 > 0 and c >= upper_5:
                signals_found.append({
                    'type':     'fib_extreme_high_5',
                    'strength': 0.85,
                    'reason':   f'Cierre de vela 15m (${c:.4f}) ≥ upper_5 (${upper_5:.4f})',
                })
            
            # SHORT: (open > bb_upper) AND (close > bb_upper) (Rompimiento Extremo Bollinger)
            if bb_upper > 0 and o > bb_upper and c > bb_upper:
                signals_found.append({
                    'type':     'bollinger_breakout_high',
                    'strength': 0.95,
                    'reason':   f'Vela 15m completamente sobre Bollinger: open (${o:.4f}) > BB_U (${bb_upper:.4f}) y close (${c:.4f}) > BB_U',
                })

    # ── SEÑAL NUEVA: Bollinger 5m con tendencia EMA20 ──────────
    if df_5m is not None and len(df_5m) >= 2:
        if 'bb_lower' not in df_5m.columns or 'ema_20' not in df_5m.columns:
            try:
                col_close_5m = 'close' if 'close' in df_5m.columns else ('c' if 'c' in df_5m.columns else '')
                if col_close_5m:
                    closes_5m = pd.to_numeric(df_5m[col_close_5m], errors='coerce').ffill()
                    rolling_mean_5m = closes_5m.rolling(window=20).mean()
                    rolling_std_5m = closes_5m.rolling(window=20).std()
                    df_5m['bb_lower'] = rolling_mean_5m - (2 * rolling_std_5m)
                    df_5m['bb_upper'] = rolling_mean_5m + (2 * rolling_std_5m)
                    df_5m['ema_3'] = closes_5m.ewm(span=3, adjust=False).mean()
                    df_5m['ema_9'] = closes_5m.ewm(span=9, adjust=False).mean()
                    df_5m['ema_20'] = closes_5m.ewm(span=20, adjust=False).mean()
                    df_5m['ema_50'] = closes_5m.ewm(span=50, adjust=False).mean()
                    df_5m['ema_200'] = closes_5m.ewm(span=200, adjust=False).mean()
                    
                    # RSI 14
                    delta = closes_5m.diff()
                    gain = delta.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                    loss = (-1 * delta.clip(upper=0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                    rs = gain / loss
                    df_5m['rsi_14'] = 100 - (100 / (1 + rs))
            except Exception as e:
                log_error('EREP_BOLLINGER_5M', f"Error calculando indicadores 5m: {e}")

        if 'bb_lower' in df_5m.columns and 'ema_20' in df_5m.columns:
            last_closed_5m = df_5m.iloc[-2]
            prev_closed_5m = df_5m.iloc[-3] if len(df_5m) >= 3 else last_closed_5m

            c_5m = float(last_closed_5m.get('close', last_closed_5m.get('c', 0)))
            o_5m = float(last_closed_5m.get('open', last_closed_5m.get('o', 0)))
            h_5m = float(last_closed_5m.get('high', last_closed_5m.get('h', 0)))
            l_5m = float(last_closed_5m.get('low', last_closed_5m.get('l', 0)))
            bb_lower_5m = float(last_closed_5m.get('bb_lower', 0))
            bb_upper_5m = float(last_closed_5m.get('bb_upper', 0))
            ema20_now = float(last_closed_5m.get('ema_20', 0))
            ema20_prev = float(prev_closed_5m.get('ema_20', 0))
            
            ema3 = float(last_closed_5m.get('ema_3', 0))
            ema9 = float(last_closed_5m.get('ema_9', 0))
            ema50 = float(last_closed_5m.get('ema_50', 0))
            ema200 = float(last_closed_5m.get('ema_200', 0))
            rsi_5m = float(last_closed_5m.get('rsi_14', 50))
            
            lower_6 = float(snap.get('lower_6', 0))
            upper_6 = float(snap.get('upper_6', 0))
            
            # SIPV helper 5m
            body_5m = c_5m - o_5m
            body_pct_5m = abs(body_5m) / (h_5m - l_5m) if (h_5m > l_5m) else 0

            if is_long:
                # Original BB + EMA20
                if bb_lower_5m > 0 and c_5m < bb_lower_5m and ema20_now < ema20_prev:
                    signals_found.append({
                        'type':     'bollinger_breakout_5m_long',
                        'strength': 0.95,
                        'reason':   f'Vela 5m bajo Bollinger ({c_5m:.4f} < {bb_lower_5m:.4f}) con EMA20 en caída',
                    })
                
                # Rule 1: Cruce LOWER_6
                if lower_6 > 0 and c_5m <= lower_6:
                    signals_found.append({
                        'type':     'fib_extreme_low_6_5m',
                        'strength': 0.95,
                        'reason':   f'Vela 5m cierra bajo LOWER_6 ({c_5m:.4f} <= {lower_6:.4f})',
                    })
                    
                # Rule 2: RSI <= 10
                if rsi_5m <= 10:
                    signals_found.append({
                        'type':     'rsi_extreme_low_5m',
                        'strength': 0.95,
                        'reason':   f'RSI 5m Extremo Bajo ({rsi_5m:.2f} <= 10)',
                    })
                    
                # Rule 3: Vela Flotante bajo BB_L
                if bb_lower_5m > 0 and o_5m < bb_lower_5m and c_5m < bb_lower_5m:
                    signals_found.append({
                        'type':     'floating_bb_low_5m',
                        'strength': 0.95,
                        'reason':   f'Vela 5m flotante bajo Bollinger (O y C < BB_L)',
                    })
                    
                # Rule 4: SIPV tras cruce BB
                c_prev = float(prev_closed_5m.get('close', prev_closed_5m.get('c', 0)))
                bb_l_prev = float(prev_closed_5m.get('bb_lower', 0))
                if bb_l_prev > 0 and c_prev < bb_l_prev and body_5m > 0 and body_pct_5m >= 0.30:
                    signals_found.append({
                        'type':     'sipv_reversal_bb_low_5m',
                        'strength': 0.95,
                        'reason':   f'SIPV Alcista (cuerpo {body_pct_5m*100:.1f}%) tras vela previa bajo BB_L',
                    })
                    
                # Rule 5: EMA Alignment
                if ema50 < ema200 and ema20 < ema50 and ema9 < ema20 and ema3 > ema9:
                    signals_found.append({
                        'type':     'ema_alignment_reversal_long_5m',
                        'strength': 0.95,
                        'reason':   f'Alineación EMA Reversión (50<200, 20<50, 9<20, 3>9)',
                    })
            else:
                # Original BB + EMA20
                if bb_upper_5m > 0 and c_5m > bb_upper_5m and ema20_now > ema20_prev:
                    signals_found.append({
                        'type':     'bollinger_breakout_5m_short',
                        'strength': 0.95,
                        'reason':   f'Vela 5m sobre Bollinger ({c_5m:.4f} > {bb_upper_5m:.4f}) con EMA20 en subida',
                    })
                    
                # Rule 1: Cruce UPPER_6
                if upper_6 > 0 and c_5m >= upper_6:
                    signals_found.append({
                        'type':     'fib_extreme_high_6_5m',
                        'strength': 0.95,
                        'reason':   f'Vela 5m cierra sobre UPPER_6 ({c_5m:.4f} >= {upper_6:.4f})',
                    })
                    
                # Rule 2: RSI >= 80
                if rsi_5m >= 80:
                    signals_found.append({
                        'type':     'rsi_extreme_high_5m',
                        'strength': 0.95,
                        'reason':   f'RSI 5m Extremo Alto ({rsi_5m:.2f} >= 80)',
                    })
                    
                # Rule 3: Vela Flotante sobre BB_U
                if bb_upper_5m > 0 and o_5m > bb_upper_5m and c_5m > bb_upper_5m:
                    signals_found.append({
                        'type':     'floating_bb_high_5m',
                        'strength': 0.95,
                        'reason':   f'Vela 5m flotante sobre Bollinger (O y C > BB_U)',
                    })
                    
                # Rule 4: SIPV tras cruce BB
                c_prev = float(prev_closed_5m.get('close', prev_closed_5m.get('c', 0)))
                bb_u_prev = float(prev_closed_5m.get('bb_upper', 0))
                if bb_u_prev > 0 and c_prev > bb_u_prev and body_5m < 0 and body_pct_5m >= 0.30:
                    signals_found.append({
                        'type':     'sipv_reversal_bb_high_5m',
                        'strength': 0.95,
                        'reason':   f'SIPV Bajista (cuerpo {body_pct_5m*100:.1f}%) tras vela previa sobre BB_U',
                    })
                    
                # Rule 5: EMA Alignment
                if ema50 > ema200 and ema20 > ema50 and ema9 > ema20 and ema3 < ema9:
                    signals_found.append({
                        'type':     'ema_alignment_reversal_short_5m',
                        'strength': 0.95,
                        'reason':   f'Alineación EMA Reversión (50>200, 20>50, 9>20, 3<9)',
                    })

    # ── SEÑAL B: Fibonacci extremo (Existente lower_6 / upper_6) ─────────────
    price = float(snap.get('price', 0))
    if is_long:
        lower_6 = float(snap.get('lower_6', 0))
        if lower_6 > 0 and price <= lower_6:
            signals_found.append({
                'type':     'fib_extreme_low',
                'strength': 0.9,
                'reason':   f'Precio ${price:.4f} ≤ lower_6 ${lower_6:.4f} (soporte extremo)',
            })
    else:
        upper_6 = float(snap.get('upper_6', 0))
        if upper_6 > 0 and price >= upper_6:
            signals_found.append({
                'type':     'fib_extreme_high',
                'strength': 0.9,
                'reason':   f'Precio ${price:.4f} ≥ upper_6 ${upper_6:.4f} (resistencia extrema)',
            })

    # ── SEÑAL C: RSI extremo ───────────────────
    rsi = float(snap.get('rsi_14', 50))
    if is_long and rsi <= rsi_oversold:
        signals_found.append({
            'type':     'rsi_oversold',
            'strength': 1.0,
            'reason':   f'RSI={rsi:.1f} ≤ {rsi_oversold} (sobreventa)',
        })
    elif not is_long and rsi >= (100 - rsi_oversold):
        signals_found.append({
            'type':     'rsi_overbought',
            'strength': 1.0,
            'reason':   f'RSI={rsi:.1f} ≥ {100-rsi_oversold} (sobrecompra)',
        })

    has_signal = len(signals_found) > 0

    return {
        'has_signal':    has_signal,
        'signals':       signals_found,
        'count':         len(signals_found),
        'best':          max(signals_found, key=lambda s: s['strength']) if signals_found else None,
        'rsi':           rsi,
        'reason': (
            ' + '.join([s['reason'] for s in signals_found]) if signals_found
            else 'Sin señal de entrada P2'
        ),
    }


# ════════════════════════════════════════════
# MÓDULO 3 — VERIFICAR CONDICIONES DE ACTIVACIÓN
# ════════════════════════════════════════════

def check_erep_activation_conditions(
    position:      dict,
    current_price: float,
    snap:          dict,
    df_15m:        pd.DataFrame,
    df_4h:         pd.DataFrame = None,
    market_type:   str = 'crypto_futures',
) -> dict:
    """
    Verifica si el EREP puede activarse.
    """
    cfg    = EREP_CONFIG.get(market_type, {})
    side   = str(position.get('side', 'long'))
    is_long = side.lower() in ('long', 'buy')

    entry_price = float(position.get(
        'avg_entry_price',
        position.get('entry_price', current_price)
    ))

    conditions = {}
    blockers   = []

    # ── C1: Ya hay EREP activo ─────────────────
    if position.get('erep_active', False):
        return {
            'can_activate': False,
            'reason': 'EREP ya está activo — solo 1 escalamiento permitido',
            'conditions': {},
        }

    # Stocks only support LONG spot
    if market_type == 'stocks_spot' and not is_long:
        return {
            'can_activate': False,
            'reason': 'Stocks solo soportan LONG en EREP',
            'conditions': {},
        }

    # ── C2: EMA3 < EMA9 ───────────────────────
    fast_p = int(cfg.get('ema_period_fast', 3))
    slow_p = int(cfg.get('ema_period_slow', 9))
    ema = get_ema_cross(df_15m, fast_p, slow_p)
    
    ema_bearish_for_long = (is_long and not ema['is_fast_above'])
    ema_bullish_for_short = (not is_long and ema['is_fast_above'])
    ema_confirms = (ema_bearish_for_long or ema_bullish_for_short)

    conditions['ema_cross'] = {
        'passed':    ema_confirms,
        'ema_fast':  ema['ema_fast'],
        'ema_slow':  ema['ema_slow'],
        'is_above':  ema['is_fast_above'],
    }
    
    if not ema_confirms:
        # EMA favorable: esperar recuperación natural
        return {
            'can_activate': False,
            'wait_natural': True,
            'reason': f'EMA favorable → esperar recuperación natural. EMA3={ema["ema_fast"]:.4f} EMA9={ema["ema_slow"]:.4f}',
            'conditions': conditions,
        }

    # ── C3: Pérdida dentro del límite ─────────
    if is_long:
        loss_pct = (entry_price - current_price) / entry_price * 100
    else:
        loss_pct = (current_price - entry_price) / entry_price * 100

    max_loss = float(cfg.get('max_loss_pct_to_activate', 6.0))
    loss_ok  = loss_pct <= max_loss

    conditions['loss_check'] = {
        'passed':    loss_ok,
        'loss_pct':  round(loss_pct, 3),
        'max_loss':  max_loss,
    }
    if not loss_ok:
        blockers.append(f'Pérdida {loss_pct:.2f}% > máximo {max_loss}% para EREP')

    # ── C4: SAR 4H no fuertemente bajista ─────
    sar_4h = int(snap.get('sar_trend_4h', 0))
    mtf    = float(snap.get('mtf_score', 0))

    if market_type == 'stocks_spot':
        sar_ok = True
        mtf_ok = True
    else:
        if is_long:
            sar_ok = sar_4h >= 0
            mtf_ok = mtf >= -0.60
        else:
            sar_ok = sar_4h <= 0
            mtf_ok = mtf <= 0.60

    conditions['sar_4h'] = {
        'passed':  sar_ok,
        'sar_4h':  sar_4h,
        'mtf':     mtf,
        'mtf_ok':  mtf_ok,
    }
    if not sar_ok:
        blockers.append(f'SAR 4H en contra ({sar_4h}) — tendencia mayor adversa')
    if not mtf_ok:
        blockers.append(f'MTF Score muy adverso ({mtf:.2f}) — sin soporte de tendencia mayor')

    # ── C5: Mercado no en caída libre ─────────
    market_drop = 0.0
    if market_type == 'stocks_spot':
        drop_ok = True
    else:
        if df_4h is not None and len(df_4h) >= 2:
            col_close = 'close' if 'close' in df_4h.columns else 'c'
            close_now  = float(df_4h.iloc[-1].get(col_close, 0))
            close_4h_ago = float(df_4h.iloc[-2].get(col_close, 0))
            if close_4h_ago > 0:
                if is_long:
                    market_drop = (close_4h_ago - close_now) / close_4h_ago * 100
                else:
                    market_drop = (close_now - close_4h_ago) / close_4h_ago * 100

        max_drop = float(cfg.get('max_drop_4h_pct', 5.0))
        drop_ok  = market_drop <= max_drop

    conditions['market_drop'] = {
        'passed':      drop_ok,
        'drop_4h_pct': round(market_drop, 2),
        'max_drop':    max_drop,
    }
    if not drop_ok:
        blockers.append(f'Mercado cayó {market_drop:.1f}% en 4H > {max_drop}% — caída fuerte')

    can_activate = len(blockers) == 0

    return {
        'can_activate': can_activate,
        'wait_natural': False,
        'blockers':     blockers,
        'loss_pct':     round(loss_pct, 3),
        'conditions':   conditions,
        'ema':          ema,
        'reason': (
            '✅ EREP puede activarse'
            if can_activate
            else f'❌ EREP bloqueado: {" | ".join(blockers)}'
        ),
    }


# ════════════════════════════════════════════
# MÓDULO 4 — EVALUAR LA FASE ACTUAL DEL EREP
# ════════════════════════════════════════════

def evaluate_erep_phase(
    position:      dict,
    current_price: float,
    snap:          dict,
    df_15m:        pd.DataFrame,
    df_4h:         pd.DataFrame = None,
    market_type:   str = 'crypto_futures',
    df_5m:         pd.DataFrame = None,
) -> dict:
    """
    Función principal del EREP.
    Evalúa qué hacer según la fase actual.
    """
    phase      = int(position.get('erep_phase', 0))
    side       = str(position.get('side', 'long'))
    is_long    = side.lower() in ('long', 'buy')
    cfg        = EREP_CONFIG.get(market_type, {})
    timeout_m  = int(cfg.get('timeout_cycles', 4))
    if market_type == 'crypto_futures':
        timeout_m = timeout_m * 3  # Scale by 3 since Crypto monitor runs every 5m instead of 15m
    cycles     = int(position.get('erep_cycles_elapsed', 0))
    p3_avg     = float(position.get('erep_p3_avg') or 0)

    fast_p = int(cfg.get('ema_period_fast', 3))
    slow_p = int(cfg.get('ema_period_slow', 9))
    ema = get_ema_cross(df_15m, fast_p, slow_p)
    is_ema_fast_above = ema['is_fast_above']

    if phase == 0:
        return {'action': 'none', 'reason': 'Fase Neutral'}

    # ── FASE 1: SL tocado ─────────────────────
    if phase == 1:
        check = check_erep_activation_conditions(
            position, current_price,
            snap, df_15m, df_4h, market_type
        )

        if check.get('wait_natural'):
            p1 = float(position.get('erep_p1_price') or 0)
            if p1 > 0:
                recovered = (is_long and current_price >= p1) or (not is_long and current_price <= p1)
                if recovered:
                    return {
                        'action':  'close_all',
                        'reason': f'RECUPERACIÓN NATURAL: EMA favorable y precio llegó a P1 ({p1:.4f}). Cerrar sin pérdidas.',
                        'close_type': 'natural_recovery',
                    }

            return {
                'action': 'wait_natural',
                'reason': check['reason'],
                'ema':    ema,
            }

        if not check['can_activate']:
            # Calcular pérdida real independientemente de si 'check' la incluyó o no
            entry_p = float(position.get('avg_entry_price', position.get('entry_price', current_price)))
            real_loss_pct = 0.0
            if entry_p > 0:
                real_loss_pct = (entry_p - current_price) / entry_p * 100 if is_long else (current_price - entry_p) / entry_p * 100

            if real_loss_pct > 0:
                # 🛡️ Si el P&L es negativo, NO cerramos. Forzamos activación de EREP Fase 2 para promedio inteligente P2.
                return {
                    'action':  'activate_phase2',
                    'reason': f'🔄 EREP FORZADO POR PNL NEGATIVO ({real_loss_pct:.2f}%): Evitando cierre en pérdida. Entrando a fase 2 para buscar rebote.',
                    'conditions': check.get('conditions', {}),
                }
            return {
                'action':   'close_sl',
                'reason': f'EREP no puede activarse: {check.get("reason", "Condición no cumplida")}. Cerrar por SL normal.',
                'close_type': 'sl_normal',
            }

        return {
            'action':  'activate_phase2',
            'reason': f'EREP activado: EMA3<EMA9, pérdida {check["loss_pct"]:.2f}% dentro del límite. Esperando señal para P2...',
            'conditions': check['conditions'],
        }

    # ── FASE 2: Esperando señal para P2 ───────
    elif phase == 2:
        entry_p = float(position.get('avg_entry_price', position.get('entry_price', current_price)))
        p1 = float(position.get('erep_p1_price') or entry_p)
        max_loss = float(cfg.get('max_loss_pct_to_activate', 6.0)) * 1.5
        current_loss = 0.0

        if p1 > 0:
            if is_long:
                current_loss = (p1 - current_price) / p1 * 100
            else:
                current_loss = (current_price - p1) / p1 * 100

        if cycles >= timeout_m:
            if current_loss > 0:
                # 🛡️ Evitar el cierre en pérdida. Aumentamos los ciclos de espera.
                return {
                    'action': 'wait_p2_signal',
                    'cycles': cycles,
                    'max':    timeout_m + 4,
                    'reason': f'🛡️ TIMEOUT EVITADO POR PNL NEGATIVO: Esperando señal P2 (ciclo {cycles}/{timeout_m + 4}).',
                }
            return {
                'action':  'close_all',
                'reason': f'TIMEOUT fase 2: {cycles}/{timeout_m} ciclos sin señal P2. Cerrar todo.',
                'close_type': 'timeout_phase2',
            }

        if p1 > 0 and current_loss > max_loss:
            # 🛡️ Si es pérdida extrema, preferimos mantenerla abierta en Modo Recuperación Virtual en vez de consolidar pérdida
            return {
                'action': 'wait_p2_signal',
                'cycles': cycles,
                'max':    timeout_m,
                'reason': f'🛡️ PÉRDIDA MÁXIMA DETECTADA ({current_loss:.2f}%): Bloqueando cierre en pérdida extrema. Esperando señal P2.',
            }

        signal = detect_p2_entry_signal(
            df_15m, snap, side, '', market_type, df_5m
        )

        if signal['has_signal']:
            return {
                'action':  'buy_p2',
                'signal':  signal,
                'reason': f'SEÑAL P2: {signal["reason"]}. Comprando segunda posición...',
            }

        return {
            'action': 'wait_p2_signal',
            'cycles': cycles,
            'max':    timeout_m,
            'reason': f'Fase 2: esperando señal P2. Ciclo {cycles}/{timeout_m}. {signal["reason"]}',
        }

    # ── FASE 3: P2 comprado, esperando P3 ─────
    elif phase == 3:
        if p3_avg <= 0:
            return {
                'action': 'close_all',
                'reason': 'P3 no calculado — cerrar',
                'close_type': 'error',
            }

        # Calcular pérdida actual para evitar cierre
        p1 = float(position.get('erep_p1_price') or position.get('entry_price') or 0)
        current_loss = 0.0
        if p1 > 0:
            current_loss = (p1 - current_price) / p1 * 100 if is_long else (current_price - p1) / p1 * 100

        if cycles >= timeout_m * 2:
            if current_loss > 0:
                # 🛡️ Evitar cierre por timeout
                return {
                    'action':   'wait_p3',
                    'p3_avg':   p3_avg,
                    'distance': round(abs(current_price - p3_avg), 6),
                    'cycles':   cycles,
                    'ema_ok':   True,
                    'reason':   f'🛡️ TIMEOUT FASE 3 EVITADO POR PNL NEGATIVO: Esperando P3 (ciclo {cycles}).',
                }
            return {
                'action':  'close_all',
                'reason': f'TIMEOUT fase 3: {cycles} ciclos. Cerrar todo.',
                'close_type': 'timeout_phase3',
            }

        # Obtener close de la última vela
        col_close = 'close' if df_15m is not None and 'close' in df_15m.columns else 'c'
        if df_15m is not None and len(df_15m) >= 2:
            last_close = float(df_15m.iloc[-2].get(col_close, current_price))
        else:
            last_close = current_price

        reached_p3 = (is_long and last_close >= p3_avg) or (not is_long and last_close <= p3_avg)

        if reached_p3:
            if is_ema_fast_above == is_long:
                return {
                    'action':  'close_all',
                    'reason': f'✅ RECUPERO EXITOSO: close {last_close:.4f} >= P3 {p3_avg:.4f} y EMA favorable. Cerrar todo con ganancia.',
                    'close_type': 'recovery_success',
                    'last_close': last_close,
                }
            else:
                return {
                    'action':  'close_all',
                    'reason': f'✅ P3 alcanzado ({last_close:.4f} >= {p3_avg:.4f}). Cerrar (EMA no ideal pero objetivo alcanzado)',
                    'close_type': 'recovery_p3',
                    'last_close': last_close,
                }

        # EMA desfavorable
        ema_unfavorable = (is_long and not is_ema_fast_above) or (not is_long and is_ema_fast_above)

        if ema_unfavorable:
            if current_loss > 0:
                # 🛡️ Evitar cierre por EMA desfavorable
                return {
                    'action':   'wait_p3',
                    'p3_avg':   p3_avg,
                    'distance': round(abs(current_price - p3_avg), 6),
                    'cycles':   cycles,
                    'ema_ok':   False,
                    'reason':   f'🛡️ EMA DESFAVORABLE EN FASE 3: Bloqueando cierre en pérdida. Esperando P3 (ciclo {cycles}).',
                }
            return {
                'action':  'close_all',
                'reason': f'EMA desfavorable en fase 3: precio {current_price:.4f} no llegó a P3 {p3_avg:.4f}. Cerrar con pérdida controlada.',
                'close_type': 'ema_unfavorable_phase3',
                'last_close': last_close,
            }

        distance = abs(current_price - p3_avg)

        return {
            'action':   'wait_p3',
            'p3_avg':   p3_avg,
            'distance': round(distance, 6),
            'cycles':   cycles,
            'ema_ok':   not ema_unfavorable,
            'reason': f'Fase 3: esperando P3. Precio={current_price:.4f} P3={p3_avg:.4f} (dist={distance:.4f}). Ciclo {cycles}',
        }

    return {
        'action': 'none',
        'reason': f'Fase EREP desconocida: {phase}',
    }


# ════════════════════════════════════════════
# SMART Q2 FIBONACCI CALCULATION MODULE
# ════════════════════════════════════════════

def find_target_fibonacci_band(
    snap:        dict,
    side:        str,
    current_price: float,
) -> dict:
    """
    Encuentra la banda Fibonacci inmediata en la dirección del recovery.
    """
    is_long = side.lower() in ('long', 'buy')

    if is_long:
        bands = []
        for n in range(1, 7):
            val = float(snap.get(f'upper_{n}', 0))
            if val > current_price:
                bands.append((f'upper_{n}', val, n))

        if not bands:
            basis = float(snap.get('basis', 0))
            if basis > current_price:
                return {'band_name': 'basis', 'band_price': basis, 'found': True}
            return {'found': False}

        bands.sort(key=lambda x: x[1])
        name, price, n = bands[0]
    else:
        bands = []
        for n in range(1, 7):
            val = float(snap.get(f'lower_{n}', 0))
            if val > 0 and val < current_price:
                bands.append((f'lower_{n}', val, n))

        if not bands:
            basis = float(snap.get('basis', 0))
            if basis < current_price:
                return {'band_name': 'basis', 'band_price': basis, 'found': True}
            return {'found': False}

        bands.sort(key=lambda x: x[1], reverse=True)
        name, price, n = bands[0]

    return {
        'band_name':  name,
        'band_price': round(price, 6),
        'band_n':     n,
        'found':      True,
        'distance_pct': abs(price - current_price) / current_price * 100,
    }


def round_q2_for_market(
    q2_raw:      float,
    market_type: str,
    cfg:         dict,
) -> float:
    """
    Redondea la cantidad Q2 según el mercado.
    """
    if market_type in ('crypto_futures', 'forex_futures'):
        decimals = int(cfg.get('round_to_decimals', 1))
        q2_rounded = round(q2_raw, decimals)
        q2_rounded = max(0.1, q2_rounded)
        return q2_rounded
    else:
        # Stocks rounding thresholds
        thresholds = cfg.get(
            'stock_round_thresholds',
            [(10, 5), (100, 10), (1000, 100), (float('inf'), 1000)]
        )
        multiple = 5
        for threshold, mult in thresholds:
            if q2_raw < threshold:
                multiple = mult
                break

        q2_rounded = round(q2_raw / multiple) * multiple
        q2_rounded = max(multiple, q2_rounded)
        return float(q2_rounded)


def calculate_q2_smart(
    p1_price:      float,
    q1:            float,
    p2_price:      float,
    snap:          dict,
    side:          str,
    market_type:   str,
) -> dict:
    """
    Calcula la cantidad óptima de P2 para que el promedio P3 sea alcanzable.
    """
    cfg = EREP_CONFIG.get(market_type, {})
    band_pct = float(cfg.get('target_band_pct', 0.95))
    
    p2_min_f = float(cfg.get('p2_min_factor', 0.5))
    p2_max_f = float(cfg.get('p2_max_factor', 3.0))

    try:
        from app.core.supabase_client import get_supabase
        sb = get_supabase()
        cfg_res = sb.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
        if cfg_res.data and 'regime_params' in cfg_res.data:
            params = cfg_res.data['regime_params'] or {}
            max_positions_val = float(params.get('erep_max_purchases', 5.0))
        else:
            max_positions_val = 5.0
    except Exception:
        max_positions_val = 5.0

    if market_type == 'stocks_spot':
        p2_min_f = 2.0
        p2_max_f = max_positions_val
    elif market_type in ('crypto_futures', 'forex_futures'):
        p2_max_f = max_positions_val

    # Buscar la banda objetivo
    band_data = find_target_fibonacci_band(snap, side, p2_price)

    if not band_data.get('found'):
        return {
            'q2_calculated':   q1,
            'q2_rounded':      q1,
            'p3_avg':          (p1_price + p2_price) / 2,
            'target_95pct':    None,
            'band_name':       'unknown',
            'method':          'fallback_equal',
            'reason':          'Sin banda Fibonacci disponible'
        }

    band_price = band_data['band_price']
    band_name  = band_data['band_name']
    is_long    = side.lower() in ('long', 'buy')

    if is_long:
        target_95 = p2_price + (band_price - p2_price) * band_pct
        if target_95 <= p2_price:
            target_95 = p2_price * 1.005
    else:
        target_95 = p2_price - (p2_price - band_price) * band_pct
        if target_95 >= p2_price:
            target_95 = p2_price * 0.995

    target_95 = round(target_95, 6)

    # Q2 = Q1 * (P1 - target_95) / (target_95 - P2)
    denominator = target_95 - p2_price
    if abs(denominator) < 0.0001:
        q2_raw = q1
        method = 'denominator_too_small'
    else:
        q2_raw = q1 * (p1_price - target_95) / denominator

    # Aplicar límites
    q2_raw = max(q1 * p2_min_f, q2_raw)
    q2_raw = min(q1 * p2_max_f, q2_raw)

    q2_rounded = round_q2_for_market(q2_raw, market_type, cfg)
    p3_real = (p1_price * q1 + p2_price * q2_rounded) / (q1 + q2_rounded)

    return {
        'q2_calculated':   round(q2_raw, 4),
        'q2_rounded':      q2_rounded,
        'p3_avg':          round(p3_real, 6),
        'p3_target':       target_95,
        'target_95pct':    target_95,
        'band_name':       band_name,
        'band_price':      band_price,
        'distance_to_band': round(band_data.get('distance_pct', 0), 2),
        'method':          'fibonacci_calculated',
        'reason':          f'Q2={q2_rounded} (raw={q2_raw:.2f}) para P3={p3_real:.4f}. Banda: {band_name}={band_price:.4f}. Target 95%={target_95:.4f}',
    }


# ════════════════════════════════════════════
# MÓDULO 5 — EJECUTAR ACCIONES EREP
# ════════════════════════════════════════════

async def execute_erep_action(
    action:        dict,
    position:      dict,
    current_price: float,
    symbol:        str,
    market_type:   str,
    supabase,
    open_func,
    close_func,
) -> dict:
    """
    Ejecuta la acción determinada por evaluate_erep_phase().
    """
    act      = action['action']
    pos_id   = position.get('id')
    side     = str(position.get('side', 'long'))
    is_long  = side.lower() in ('long', 'buy')
    cfg      = EREP_CONFIG.get(market_type, {})

    table = (
        'positions'
        if market_type == 'crypto_futures'
        else 'forex_positions'
        if market_type == 'forex_futures'
        else 'stocks_positions'
    )

    from app.workers.alerts_service import send_telegram_message

    async def send_telegram_local(msg):
        try:
            await send_telegram_message(msg)
        except Exception:
            pass

    # ── ACTIVAR FASE 2 ────────────────────────
    if act == 'activate_phase2':
        p1_price = float(position.get('avg_entry_price', position.get('entry_price', current_price)))
        p1_size  = float(position.get('size', position.get('shares', 0.01)))

        update_fields = {
            'erep_active':          True,
            'erep_phase':           2,
            'erep_p1_price':        p1_price,
            'erep_p1_size':         p1_size,
            'erep_q1':              p1_size,
            'erep_activated_at':    datetime.now(timezone.utc).isoformat(),
            'erep_cycles_elapsed':  0,
        }
        if table == 'positions':
            update_fields['sl_type'] = 'erep_suspended'
            update_fields['stop_loss'] = 0
            update_fields['sl_price'] = 0
        elif table == 'forex_positions':
            update_fields['sl_price'] = 0
        else:
            update_fields['stop_loss'] = 0
            update_fields['sl_price'] = 0

        supabase.table(table).update(update_fields).eq('id', pos_id).execute()

        log_info('EREP', f'🟢 EREP ACTIVADO [{symbol}] ({side.upper()}): Fase 1→2. P1={p1_price:.4f} size={p1_size}. Esperando señal para P2...')

        await send_telegram_local(
            f'🔄 EREP ACTIVADO [{symbol}] {side.upper()}\n'
            f'P1: ${p1_price:.4f} ({p1_size} unidades)\n'
            f'⏳ Esperando señal para P2...\n'
            f'Máx: {cfg["timeout_cycles"]} ciclos'
        )
        return {'executed': 'phase2_activated'}

    # ── COMPRAR P2 ────────────────────────────
    elif act == 'buy_p2':
        p1_price = float(position.get('erep_p1_price') or 0)
        p1_size  = float(position.get('erep_p1_size') or position.get('erep_q1') or 0.01)
        
        # Intentar cálculo inteligente de Q2 con Fibonacci
        q2_data = calculate_q2_smart(
            p1_price    = p1_price,
            q1          = p1_size,
            p2_price    = current_price,
            snap        = action.get('snap', snap_or_empty := {}),
            side        = side,
            market_type = market_type,
        )

        if q2_data.get('method') == 'fibonacci_calculated':
            p2_size = q2_data['q2_rounded']
            p3_avg  = q2_data['p3_avg']
            target_price = q2_data.get('p3_target', p3_avg)
            band_name  = q2_data.get('band_name', '')
            band_price = q2_data.get('band_price', 0)
            reason_str = q2_data['reason']
        else:
            p2_size  = p1_size * float(cfg.get('p2_size_factor', 1.0))
            p2_size = round_q2_for_market(p2_size, market_type, cfg)
            p3_avg = (p1_price * p1_size + current_price * p2_size) / (p1_size + p2_size)
            target_price = p3_avg
            band_name = 'fallback_equal'
            band_price = 0
            reason_str = f"P2={p2_size} (factor={cfg.get('p2_size_factor', 1.0)})"

        log_info('EREP', f'🛒 EREP P2 [{symbol}] {side.upper()}: comprando {p2_size} @ {current_price:.4f}. P3={p3_avg:.4f}')

        # Abrir la segunda posición
        try:
            await open_func(
                symbol    = symbol,
                side      = side,
                size      = p2_size,
                price     = current_price,
                reason    = 'EREP_P2',
                supabase  = supabase,
            )
        except Exception as e:
            log_error('EREP', f'Error P2: {e}')
            return {'executed': 'error_p2'}

        # Actualizar la posición original
        supabase.table(table).update({
            'erep_phase':             3,
            'erep_p2_price':          current_price,
            'erep_p2_size':           p2_size,
            'erep_q2_calculated':     q2_data.get('q2_calculated', p2_size),
            'erep_q2_rounded':        p2_size,
            'erep_p3_avg':            round(p3_avg, 6),
            'erep_p3_recalculated':   round(p3_avg, 6),
            'erep_target_price':      round(target_price, 6),
            'erep_target_band':       band_name,
            'erep_target_band_price': band_price,
            'erep_target_95pct':      round(target_price, 6),
            'erep_cycles_elapsed':    0,
        }).eq('id', pos_id).execute()

        await send_telegram_local(
            f'🛒 EREP P2 COMPRADO [{symbol}] {side.upper()}\n'
            f'P1: ${p1_price:.4f} ({p1_size} u)\n'
            f'P2: ${current_price:.4f} ({p2_size} u)\n'
            f'P3 (target): ${p3_avg:.4f}\n'
            f'Banda obj: {band_name}={band_price:.4f}\n'
            f'Razón: {reason_str}\n'
            f'⏳ Esperando recuperación a P3...'
        )
        return {
            'executed': 'p2_bought',
            'p2_price': current_price,
            'p3_avg':   p3_avg,
        }

    # ── CERRAR TODAS LAS POSICIONES ───────────
    elif act in ('close_all', 'close_sl', 'close_tp'):
        close_type = action.get('close_type', 'erep_close')
        if act == 'close_tp':
            close_type = 'recovery_success'
        elif act == 'close_sl':
            close_type = 'sl_normal'

        size = float(position.get('shares_remaining', position.get('shares', position.get('size', 0.01))))

        log_info('EREP', f'{"✅" if "success" in close_type else "🔴"} EREP CIERRE [{symbol}] ({side.upper()}): {action.get("reason", "")}')

        # Cerrar la posición principal (con reintentos por fallos de red)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await close_func(
                    symbol       = symbol,
                    side         = side,
                    size         = size,
                    price        = current_price,
                    reason       = f'EREP_{close_type.upper()}',
                    supabase     = supabase,
                )
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    log_warning('EREP', f'Error P1 close attempt {attempt+1}: {e}. Retrying in 1s...')
                    await asyncio.sleep(1.0)
                else:
                    log_error('EREP', f'Error P1 close final: {e}')

        # Limpiar campos EREP en base de datos e incorporar campos de cierre principales
        for attempt in range(max_retries):
            try:
                supabase.table(table).update({
                    'erep_active':       False,
                    'erep_phase':        0,
                    'erep_close_reason': close_type,
                    'status':            'closed',
                    'closed_at':         datetime.now(timezone.utc).isoformat(),
                    'close_reason':      f'EREP_{close_type.upper()}'[:50]
                }).eq('id', pos_id).execute()
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    log_warning('EREP', f'Error P1 DB update attempt {attempt+1}: {e}. Retrying in 1s...')
                    await asyncio.sleep(1.0)
                else:
                    log_error('EREP', f'Error P1 DB update final: {e}')

        # Calcular P&L del EREP completo
        p1_price = float(position.get('erep_p1_price') or position.get('entry_price', current_price))
        pnl_erep = (current_price - p1_price) / p1_price * 100 if p1_price > 0 else 0
        if str(side).lower() in ('short', 'sell'):
            pnl_erep = -pnl_erep

        emoji = '✅' if pnl_erep >= 0 else '🔴'

        await send_telegram_local(
            f'{emoji} EREP CERRADO [{symbol}] {side.upper()}\n'
            f'Tipo: {close_type}\n'
            f'P1: ${p1_price:.4f}\n'
            f'Precio salida: ${current_price:.4f}\n'
            f'P&L: {pnl_erep:+.3f}%\n'
            f'Razón: {action.get("reason", "")[:100]}'
        )

        return {
            'executed': 'closed',
            'close_type': close_type,
            'pnl_pct':  pnl_erep,
        }

    # ── INCREMENTAR CICLOS ────────────────────
    elif act in ('wait_p2_signal', 'wait_p3', 'wait_natural', 'increment_cycle'):
        cycles = int(position.get('erep_cycles_elapsed', 0)) + 1
        supabase.table(table).update({
            'erep_cycles_elapsed': cycles
        }).eq('id', pos_id).execute()

        return {'executed': 'waiting', 'action': act}

    return {'executed': 'none'}
