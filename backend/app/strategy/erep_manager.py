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

_erep_p2_notified_set = set()

# ── EREP CONFIGURATION (PASO 1 & 2) ──
EREP_CONFIG = {
    'crypto_futures': {
        # ── User's new config keys ──
        'early_activation_min_loss_pct': 0.5,
        'max_loss_pct_to_activate': 6.0,
        # Si pérdida > 6% → NO activar EREP
        'p2_size_factor':           1.0,
        # P2 = P1 × 1.0 (mismo tamaño)
        'timeout_cycles':           4,
        # máximo 4 ciclos de 15m = 1 hora
        'max_drop_4h_pct':          5.0,
        # Si el mercado cayó >5% en 4H → no EREP
        'rsi_oversold':             25,
        # RSI <= 25 → comprar P2
        'ema_period_fast':          3,
        # EMA rápida (EMA3)
        'ema_period_slow':          9,
        # EMA lenta (EMA9)
        'min_pips_recovery':        0.35,
        # cerrar si ganancia > 0.35% (cubre fees de Binance y asegura ganancia)

        # ── Previous config keys ──
        'rsi_oversold_long':        25,
        'rsi_overbought_short':     75,
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
        'early_activation_min_loss_pct': 0.15,
        'max_loss_pct_to_activate': 1.5,
        'p2_size_factor':           1.0,
        'timeout_cycles':           4,
        'max_drop_4h_pct':          2.0,
        'rsi_oversold':             15,
        'ema_period_fast':          3,
        'ema_period_slow':          9,
        'min_pips_recovery':        2,

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
        'early_activation_min_loss_pct': 1.5,
        'max_loss_pct_to_activate': 8.0,
        'p2_size_factor':           1.0,
        'timeout_cycles':           6,
        'max_drop_4h_pct':          10.0,
        'rsi_oversold':             20,
        'ema_period_fast':          3,
        'ema_period_slow':          9,
        'min_pips_recovery':        0.15,

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
    entry_price: float = 0.0,
    df_1h:     pd.DataFrame = None,
    df_1d:     pd.DataFrame = None,
    df_4h:     pd.DataFrame = None,
) -> dict:
    """
    Detecta la señal para comprar P2.
    Supports LONG, SHORT, Crypto, Forex, and Stocks.
    Incluye detección de soporte/resistencia en Bollinger 1H y alineación Macro 1D / 4H.
    """
    cfg   = EREP_CONFIG.get(market_type, {})
    snap  = snap or {}
    rsi_oversold = int(cfg.get('rsi_oversold', 10))
    signals_found = []

    is_long = side.lower() in ('long', 'buy')

    # ── SEÑAL 1H: Soporte/Resistencia en Banda de Bollinger 1H ──────────
    if df_1h is not None and len(df_1h) >= 20:
        try:
            col_close_1h = 'close' if 'close' in df_1h.columns else ('c' if 'c' in df_1h.columns else '')
            if col_close_1h:
                c1h = pd.to_numeric(df_1h[col_close_1h], errors='coerce').ffill()
                m1h = c1h.rolling(20).mean().iloc[-1]
                s1h = c1h.rolling(20).std().iloc[-1]
                bb_lower_1h = m1h - 2.0 * s1h
                bb_upper_1h = m1h + 2.0 * s1h
                
                last_1h = df_1h.iloc[-1]
                c_now_1h = float(last_1h.get('close', last_1h.get('c', 0)))
                l_now_1h = float(last_1h.get('low', last_1h.get('l', 0)))
                h_now_1h = float(last_1h.get('high', last_1h.get('h', 0)))
                
                if is_long and (l_now_1h <= (bb_lower_1h * 1.002) or c_now_1h <= (bb_lower_1h * 1.002)):
                    signals_found.append({
                        'type':     'bollinger_1h_support',
                        'strength': 0.95,
                        'reason':   f'Toque de Soporte en Banda Inferior Bollinger 1H (${bb_lower_1h:.4f})',
                    })
                elif not is_long and (h_now_1h >= (bb_upper_1h * 0.998) or c_now_1h >= (bb_upper_1h * 0.998)):
                    signals_found.append({
                        'type':     'bollinger_1h_resistance',
                        'strength': 0.95,
                        'reason':   f'Toque de Resistencia en Banda Superior Bollinger 1H (${bb_upper_1h:.4f})',
                    })
        except Exception as e:
            log_error('EREP_BOLLINGER_1H', f"Error calculando Bollinger 1H: {e}")

    # ── SEÑAL MACRO 1D: Alineación con Tendencia Diaria ──────────
    if df_1d is not None and len(df_1d) >= 2:
        try:
            col_close_1d = 'close' if 'close' in df_1d.columns else ('c' if 'c' in df_1d.columns else '')
            if col_close_1d:
                c1d = pd.to_numeric(df_1d[col_close_1d], errors='coerce').ffill()
                e3_1d = float(c1d.ewm(span=3, adjust=False).mean().iloc[-1])
                e3_prev = float(c1d.ewm(span=3, adjust=False).mean().iloc[-2])
                e9_1d = float(c1d.ewm(span=9, adjust=False).mean().iloc[-1])
                if is_long and (e3_1d >= e9_1d or e3_1d >= e3_prev):
                    signals_found.append({
                        'type':     'macro_1d_aligned',
                        'strength': 0.90,
                        'reason':   f'Tendencia Macro 1D Alcista (EMA3={e3_1d:.4f} ascendente)',
                    })
                elif not is_long and (e3_1d <= e9_1d or e3_1d <= e3_prev):
                    signals_found.append({
                        'type':     'macro_1d_aligned',
                        'strength': 0.90,
                        'reason':   f'Tendencia Macro 1D Bajista (EMA3={e3_1d:.4f} descendente)',
                    })
        except Exception as e:
            log_error('EREP_MACRO_1D', f"Error calculando Macro 1D: {e}")

    # ── SEÑAL MACRO 4H: Alineación con Tendencia Estructural 4H ──────────
    if df_4h is not None and len(df_4h) >= 2:
        try:
            col_close_4h = 'close' if 'close' in df_4h.columns else ('c' if 'c' in df_4h.columns else '')
            if col_close_4h:
                c4h = pd.to_numeric(df_4h[col_close_4h], errors='coerce').ffill()
                e3_4h = float(c4h.ewm(span=3, adjust=False).mean().iloc[-1])
                e3_4h_prev = float(c4h.ewm(span=3, adjust=False).mean().iloc[-2])
                e9_4h = float(c4h.ewm(span=9, adjust=False).mean().iloc[-1])
                if is_long and (e3_4h >= e9_4h or e3_4h >= e3_4h_prev):
                    signals_found.append({
                        'type':     'macro_4h_aligned',
                        'strength': 0.90,
                        'reason':   f'Tendencia Macro 4H Alcista (EMA3={e3_4h:.4f} ascendente)',
                    })
                elif not is_long and (e3_4h <= e9_4h or e3_4h <= e3_4h_prev):
                    signals_found.append({
                        'type':     'macro_4h_aligned',
                        'strength': 0.90,
                        'reason':   f'Tendencia Macro 4H Bajista (EMA3={e3_4h:.4f} descendente)',
                    })
        except Exception as e:
            log_error('EREP_MACRO_4H', f"Error calculando Macro 4H: {e}")

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
            
            # Dynamic Capitulation Settings
            if market_type == 'forex_futures':
                capitulation_rsi_low = 25
                capitulation_rsi_high = 75
                needs_pin_bar = True
            else:
                capitulation_rsi_low = 30
                capitulation_rsi_high = 70
                needs_pin_bar = False

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
                    
                # Rule 2: RSI <= 10 (Original)
                if rsi_5m <= 10:
                    signals_found.append({
                        'type':     'rsi_extreme_low_5m',
                        'strength': 0.95,
                        'reason':   f'RSI 5m Extremo Bajo ({rsi_5m:.2f} <= 10)',
                    })
                    
                # ── NUEVA REGLA: Capitulación Extrema 5m ──
                if bb_lower_5m > 0 and c_5m < bb_lower_5m and c_5m < o_5m and rsi_5m <= capitulation_rsi_low:
                    pin_bar_ok = True
                    if needs_pin_bar:
                        lower_wick_pct = (c_5m - l_5m) / (h_5m - l_5m) if (h_5m > l_5m) else 0
                        pin_bar_ok = lower_wick_pct >= 0.30
                        
                    if pin_bar_ok:
                        extra_reason = " con Mecha de Rechazo (Pin Bar)" if needs_pin_bar else ""
                        signals_found.append({
                            'type':     'bollinger_capitulation_5m',
                            'strength': 1.0, # Fuerza Máxima
                            'reason':   f'Capitulación 5m: RSI={rsi_5m:.1f} <= {capitulation_rsi_low}, Vela Roja fuera de BB{extra_reason}',
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
                    
                # ── NUEVA REGLA: Capitulación Extrema 5m SHORT ──
                if bb_upper_5m > 0 and c_5m > bb_upper_5m and c_5m > o_5m and rsi_5m >= capitulation_rsi_high:
                    pin_bar_ok = True
                    if needs_pin_bar:
                        upper_wick_pct = (h_5m - c_5m) / (h_5m - l_5m) if (h_5m > l_5m) else 0
                        pin_bar_ok = upper_wick_pct >= 0.30
                        
                    if pin_bar_ok:
                        extra_reason = " con Mecha de Rechazo (Pin Bar)" if needs_pin_bar else ""
                        signals_found.append({
                            'type':     'bollinger_capitulation_5m_short',
                            'strength': 1.0, # Fuerza Máxima
                            'reason':   f'Capitulación SHORT 5m: RSI={rsi_5m:.1f} >= {capitulation_rsi_high}, Vela Verde fuera de BB{extra_reason}',
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

    # ── SEÑAL B: Cascada Fibonacci de Grado Inferior / Superior (LOWER_3 a LOWER_6 / UPPER_3 a UPPER_6) ──
    price = float(snap.get('price', 0))
    if price <= 0 and df_15m is not None and not df_15m.empty:
        col_c = 'close' if 'close' in df_15m.columns else ('c' if 'c' in df_15m.columns else '')
        if col_c:
            price = float(df_15m[col_c].iloc[-1])

    if entry_price > 0 and price > 0:
        fib_ladder = get_fibonacci_erep_target(entry_price, price, side, snap)
        if fib_ladder.get('reached'):
            t_band = fib_ladder.get('target_band', '').upper()
            t_px = fib_ladder.get('target_price', 0.0)
            signals_found.append({
                'type':     f'fib_ladder_{fib_ladder.get("target_band")}',
                'strength': 1.0,
                'reason':   f'Cascada EREP: precio ${price:.4f} alcanzó banda de menor grado {t_band} (${t_px:.4f})',
            })

    # Soporte / Resistencia Extrema Fibonacci (lower_6 / upper_6)
    if is_long:
        lower_6 = float(snap.get('lower_6', 0))
        if lower_6 > 0 and price <= lower_6:
            signals_found.append({
                'type':     'fib_extreme_low',
                'strength': 0.95,
                'reason':   f'Precio ${price:.4f} ≤ lower_6 ${lower_6:.4f} (soporte extremo)',
            })
    else:
        upper_6 = float(snap.get('upper_6', 0))
        if upper_6 > 0 and price >= upper_6:
            signals_found.append({
                'type':     'fib_extreme_high',
                'strength': 0.95,
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

    # ── SEÑAL D: Soporte / Resistencia Institucional en EMA9 / EMA20 (1h / 4h) ──
    ema9_4h = float(snap.get('ema9_4h') or snap.get('ema_9_4h') or 0.0)
    ema20_4h = float(snap.get('ema20_4h') or snap.get('ema_20_4h') or 0.0)
    ema9_1h = float(snap.get('ema9_1h') or snap.get('ema_9_1h') or 0.0)
    ema20_1h = float(snap.get('ema20_1h') or snap.get('ema_20_1h') or 0.0)

    ema_tol = 0.0020 if ('crypto' in str(market_type).lower() or 'USDT' in str(symbol).upper()) else 0.0006
    if is_long:
        for ema_val, name in [(ema9_4h, "EMA9_4h"), (ema20_4h, "EMA20_4h"), (ema9_1h, "EMA9_1h"), (ema20_1h, "EMA20_1h")]:
            if ema_val > 0 and price > 0 and abs(price - ema_val) / ema_val <= ema_tol:
                signals_found.append({
                    'type': f'ema_support_{name.lower()}',
                    'strength': 0.95,
                    'reason': f'Rebote soporte institucional en {name} (${ema_val:.4f}) testea precio ${price:.4f}',
                })
                break
    else:
        for ema_val, name in [(ema9_4h, "EMA9_4h"), (ema20_4h, "EMA20_4h"), (ema9_1h, "EMA9_1h"), (ema20_1h, "EMA20_1h")]:
            if ema_val > 0 and price > 0 and abs(price - ema_val) / ema_val <= ema_tol:
                signals_found.append({
                    'type': f'ema_resistance_{name.lower()}',
                    'strength': 0.95,
                    'reason': f'Rechazo resistencia institucional en {name} (${ema_val:.4f}) testea precio ${price:.4f}',
                })
                break

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
    df_5m:         pd.DataFrame = None,
    df_1h:         pd.DataFrame = None,
    df_1d:         pd.DataFrame = None,
) -> dict:
    """
    Verifica si el EREP puede activarse.
    """
    cfg    = EREP_CONFIG.get(market_type, {})
    snap   = snap or {}
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
    
    # ── BYPASS DE 5 MINUTOS (Si el colapso es abrupto) ──
    bypass_15m = False
    if not ema_confirms and df_5m is not None and len(df_5m) >= 20:
        c5 = pd.to_numeric(df_5m['close' if 'close' in df_5m.columns else 'Close'], errors='coerce').dropna()
        if len(c5) >= 20:
            ema3_5 = float(c5.ewm(span=3, adjust=False).mean().iloc[-1])
            ema9_5 = float(c5.ewm(span=9, adjust=False).mean().iloc[-1])
            ema20_5 = float(c5.ewm(span=20, adjust=False).mean().iloc[-1])
            
            if is_long and (ema3_5 < ema9_5 < ema20_5):
                bypass_15m = True
            elif not is_long and (ema3_5 > ema9_5 > ema20_5):
                bypass_15m = True
                
    if not ema_confirms and not bypass_15m:
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
        # Si Macro 1D o 4H está alineado con la posición, anula bloqueos de SAR 4H / MTF
        macro_aligned = False
        if df_1d is not None and len(df_1d) >= 2:
            col_c1d = 'close' if 'close' in df_1d.columns else ('c' if 'c' in df_1d.columns else '')
            if col_c1d:
                c1d = pd.to_numeric(df_1d[col_c1d], errors='coerce').ffill()
                e3_1d = float(c1d.ewm(span=3, adjust=False).mean().iloc[-1])
                e3_prev = float(c1d.ewm(span=3, adjust=False).mean().iloc[-2])
                e9_1d = float(c1d.ewm(span=9, adjust=False).mean().iloc[-1])
                if is_long and (e3_1d >= e9_1d or e3_1d >= e3_prev):
                    macro_aligned = True
                elif not is_long and (e3_1d <= e9_1d or e3_1d <= e3_prev):
                    macro_aligned = True

        if not macro_aligned and df_4h is not None and len(df_4h) >= 2:
            col_c4h = 'close' if 'close' in df_4h.columns else ('c' if 'c' in df_4h.columns else '')
            if col_c4h:
                c4h = pd.to_numeric(df_4h[col_c4h], errors='coerce').ffill()
                e3_4h = float(c4h.ewm(span=3, adjust=False).mean().iloc[-1])
                e3_4h_prev = float(c4h.ewm(span=3, adjust=False).mean().iloc[-2])
                e9_4h = float(c4h.ewm(span=9, adjust=False).mean().iloc[-1])
                if is_long and (e3_4h >= e9_4h or e3_4h >= e3_4h_prev):
                    macro_aligned = True
                elif not is_long and (e3_4h <= e9_4h or e3_4h <= e3_4h_prev):
                    macro_aligned = True

        if macro_aligned:
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
    df_1h:         pd.DataFrame = None,
    df_1d:         pd.DataFrame = None,
) -> dict:
    """
    Función principal del EREP.
    Evalúa qué hacer según la fase actual.
    """
    if position.get('status') == 'closed':
        return {'action': 'none', 'reason': 'Posicion ya cerrada'}
    snap       = snap or {}
    phase      = int(position.get('erep_phase', 0))
    if position.get('erep_p2_price') and float(position.get('erep_p2_price') or 0) > 0:
        phase = 3
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

    # ── PROTECCIÓN CRÍTICA: QUIEBRE ESTRUCTURAL CATASTRÓFICO (Hard Floor / Ceiling) ──
    atr_val = float(snap.get('atr', 0))
    if atr_val <= 0 and df_15m is not None and len(df_15m) >= 5:
        col_c = 'close' if 'close' in df_15m.columns else ('c' if 'c' in df_15m.columns else '')
        if col_c:
            atr_val = float(pd.to_numeric(df_15m[col_c], errors='coerce').std() * 0.5)
    if atr_val <= 0:
        atr_val = current_price * 0.015

    if is_long:
        lower_6_val = float(snap.get('lower_6', 0))
        if lower_6_val > 0 and current_price <= (lower_6_val - 1.2 * atr_val):
            return {
                'action': 'close_all',
                'close_type': 'erep_structural_breakdown',
                'reason': f'🚨 QUIEBRE ESTRUCTURAL CATASTRÓFICO: Precio ${current_price:.4f} perforó suelo LOWER_6 (${lower_6_val:.4f} - 1.2*ATR). Cierre definitivo para salvaguardar capital.',
            }
    else:
        upper_6_val = float(snap.get('upper_6', 0))
        if upper_6_val > 0 and current_price >= (upper_6_val + 1.2 * atr_val):
            return {
                'action': 'close_all',
                'close_type': 'erep_structural_breakdown',
                'reason': f'🚨 QUIEBRE ESTRUCTURAL CATASTRÓFICO: Precio ${current_price:.4f} superó techo UPPER_6 (${upper_6_val:.4f} + 1.2*ATR). Cierre definitivo para salvaguardar capital.',
            }

    # ── FASE 1: SL tocado ─────────────────────
    if phase == 1:
        check = check_erep_activation_conditions(
            position, current_price,
            snap, df_15m, df_4h, market_type, df_5m,
            df_1h=df_1h, df_1d=df_1d
        )

        if check.get('wait_natural'):
            p1 = float(position.get('erep_p1_price') or 0)
            if p1 > 0:
                cfg_min_pips = float(cfg.get('min_pips_recovery', 0))
                
                # Dinamizar pips según lote (1 pip = $10 USD por lote standard)
                # target_usd_min = 1.00 USD
                lots_qty = float(position.get('lots', position.get('size', 1.0)))
                required_pips = 1.00 / (10.0 * max(0.01, abs(lots_qty))) if lots_qty > 0 else cfg_min_pips
                min_pips = max(cfg_min_pips, required_pips)
                
                buffer_price = 0.0
                if market_type == 'forex_futures':
                    pip_sizes = {'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'USDJPY': 0.01, 'USDCHF': 0.0001, 'XAUUSD': 0.01, 'AUDUSD': 0.0001}
                    sym = position.get('symbol', '')
                    pip_size = pip_sizes.get(sym, 0.0001)
                    buffer_price = min_pips * pip_size
                else:
                    buffer_price = p1 * (min_pips / 100.0)

                target_p1 = p1 + buffer_price if is_long else p1 - buffer_price
                recovered = (is_long and current_price >= target_p1) or (not is_long and current_price <= target_p1)
                
                if recovered:
                    return {
                        'action':  'close_all',
                        'reason': f'RECUPERACIÓN NATURAL: EMA favorable y precio llegó a {target_p1:.4f} (P1 + margen). Cerrar asegurando >$1.00 ganancias.',
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
            # 🛡️ Si P&L es positivo o neutro (real_loss_pct <= 0), NUNCA cerrar por SL normal.
            # Dejar correr la posición hacia su objetivo o recuperación natural.
            return {
                'action':   'wait_natural',
                'reason': f'Posición en ganancia/breakeven ({real_loss_pct:.2f}%). EREP en espera de maduración hacia TP.',
                'conditions': check.get('conditions', {}),
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
            df_15m, snap, side, '', market_type, df_5m, entry_price=p1,
            df_1h=df_1h, df_1d=df_1d, df_4h=df_4h
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

        # Calcular pérdida actual usando el promedio de posiciones (p3_avg)
        current_loss = 0.0
        if p3_avg > 0:
            current_loss = (p3_avg - current_price) / p3_avg * 100 if is_long else (current_price - p3_avg) / p3_avg * 100

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

        # Garantizar que estamos en ganancia respecto al PROMEDIO de posiciones (p3_avg)
        cfg_min_pips = float(cfg.get('min_pips_recovery', 0))
        
        # Dinamizar pips según lote total (1 pip = $10 USD por lote standard)
        # target_usd_min = 1.00 USD
        lots_qty = float(position.get('lots', position.get('size', 1.0)))
        # Para crypto o forex, adaptamos. En forex usamos lots.
        required_pips = 1.00 / (10.0 * max(0.01, abs(lots_qty))) if lots_qty > 0 else cfg_min_pips
        min_pips = max(cfg_min_pips, required_pips)
        
        target_margin_pct = 0.0
        
        if market_type == 'forex_futures' and p3_avg > 0:
            pip_sizes = {'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'USDJPY': 0.01, 'USDCHF': 0.0001, 'XAUUSD': 0.01, 'AUDUSD': 0.0001}
            sym = position.get('symbol', '')
            pip_size = pip_sizes.get(sym, 0.0001)
            target_margin_pct = -((min_pips * pip_size) / p3_avg * 100)
        else:
            target_margin_pct = -min_pips

        reached_p3 = (current_loss <= target_margin_pct) or (current_loss <= 0.0)
        last_close = current_price

        # Bandas de Bollinger objetivo para Clímax / Runner
        upper_bb = float(snap.get('upper_band') or snap.get('upper_5') or 0.0)
        lower_bb = float(snap.get('lower_band') or snap.get('lower_5') or 0.0)
        if upper_bb <= 0 and df_15m is not None and len(df_15m) >= 20:
            c_col = 'close' if 'close' in df_15m.columns else ('c' if 'c' in df_15m.columns else '')
            if c_col:
                c15_s = pd.to_numeric(df_15m[c_col], errors='coerce').dropna()
                if len(c15_s) >= 20:
                    upper_bb = float(c15_s.rolling(20).mean().iloc[-1] + 2 * c15_s.rolling(20).std().iloc[-1])
                    lower_bb = float(c15_s.rolling(20).mean().iloc[-1] - 2 * c15_s.rolling(20).std().iloc[-1])

        # Pendiente EMA3 en 15m / 5m
        ema3_slope_favorable = False
        df_for_slope = df_15m if df_15m is not None and len(df_15m) >= 3 else (df_5m if df_5m is not None and len(df_5m) >= 3 else None)
        if df_for_slope is not None and len(df_for_slope) >= 3:
            c_col_sl = 'close' if 'close' in df_for_slope.columns else ('c' if 'c' in df_for_slope.columns else '')
            if c_col_sl:
                c_sl = pd.to_numeric(df_for_slope[c_col_sl], errors='coerce').dropna()
                if len(c_sl) >= 3:
                    e3_s = c_sl.ewm(span=3, adjust=False).mean()
                    sl_diff = float(e3_s.iloc[-1] - e3_s.iloc[-2])
                    ema3_slope_favorable = (sl_diff > 0) if is_long else (sl_diff < 0)

        is_runner_active = bool(position.get('erep_runner_active'))

        # ── 1. OBJETIVO CLÍMAX SUPERIOR / INFERIOR: Tocar la Banda Bollinger ──
        if is_long and upper_bb > p3_avg and last_close >= (upper_bb * 0.999):
            return {
                'action': 'close_all',
                'reason': f'🎯 TP CLÍMAX BANDA SUPERIOR: close {last_close:.4f} >= Upper_BB {upper_bb:.4f}. Cierre masivo con máxima ganancia!',
                'close_type': 'tp_upper_bb_runner',
                'last_close': last_close,
            }
        elif (not is_long) and lower_bb > 0 and lower_bb < p3_avg and last_close <= (lower_bb * 1.001):
            return {
                'action': 'close_all',
                'reason': f'🎯 TP CLÍMAX BANDA INFERIOR: close {last_close:.4f} <= Lower_BB {lower_bb:.4f}. Cierre masivo con máxima ganancia!',
                'close_type': 'tp_lower_bb_runner',
                'last_close': last_close,
            }

        if reached_p3:
            # ── 2. EVALUACIÓN DE INERCIA EMA3 AL TOCAR P3 (Break-Even) ──
            # Si EMA3 se mantiene favorable: PROHIBIDO CERRAR EN P3. Blindar SL y mantener RUNNER hacia Banda Bollinger
            if (is_ema_fast_above == is_long) or ema3_slope_favorable:
                buffer_pip = (min_pips * pip_size) if market_type == 'forex_futures' else (p3_avg * 0.001)
                new_sl = round(p3_avg + buffer_pip, 6) if is_long else round(p3_avg - buffer_pip, 6)
                target_bb = upper_bb if is_long else lower_bb
                return {
                    'action': 'hold_runner_to_bb',
                    'new_sl': new_sl,
                    'p3_avg': p3_avg,
                    'target_bb': target_bb,
                    'reason': f'🏃 EREP RUNNER ACTIVO: P3 {p3_avg:.4f} alcanzado con EMA3 favorable. Prohibido cerrar en BE; SL blindado a {new_sl:.4f} y acompañando hacia Banda {"Superior" if is_long else "Inferior"} ({target_bb:.4f}).',
                    'last_close': last_close,
                }

            # ── 3. SALIDA POR AGOTAMIENTO SI RUNNER YA ESTABA ACTIVO ──
            if is_runner_active and not ema3_slope_favorable and (is_ema_fast_above != is_long):
                return {
                    'action': 'close_all',
                    'reason': f'⚠️ SALIDA POR AGOTAMIENTO EMA3: Momentum se agotó por encima de P3 ({last_close:.4f} vs P3 {p3_avg:.4f}). Cerrando para asegurar ganancia.',
                    'close_type': 'tp_ema3_exhaustion',
                    'last_close': last_close,
                }

            # ── 4. SALIDA DEFENSIVA ESTÁNDAR SI EMA ES PLANA/DESFAVORABLE ──
            return {
                'action':  'close_all',
                'reason': f'✅ P3 alcanzado ({last_close:.4f} >= {p3_avg:.4f}). EMA plana/desfavorable -> Cierre defensivo Break-Even estándar.',
                'close_type': 'recovery_p3',
                'last_close': last_close,
            }

        # EMA desfavorable
        ema_unfavorable = (is_long and not is_ema_fast_above) or (not is_long and is_ema_fast_above)

        if ema_unfavorable:
            if current_loss > target_margin_pct:
                # 🛡️ Bloquear cierre prematuro: esperar a alcanzar el margen mínimo de ganancia (+min_pips)
                return {
                    'action':   'wait_p3',
                    'p3_avg':   p3_avg,
                    'distance': round(abs(current_price - p3_avg), 6),
                    'cycles':   cycles,
                    'ema_ok':   False,
                    'reason':   f'🛡️ EMA DESFAVORABLE EN FASE 3: Protegiendo trade recuperado. Esperando alcanzar ganancia mínima objetivo {abs(target_margin_pct):.2f}% (ciclo {cycles}).',
                }
            return {
                'action':  'close_all',
                'reason': f'✅ Recuperación EREP asegurada en EMA desfavorable: ganancia {abs(current_loss):.2f}% >= {abs(target_margin_pct):.2f}%.',
                'close_type': 'recovery_success_ema_exit',
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

def get_fibonacci_erep_target(
    entry_price: float,
    current_price: float,
    side: str,
    snap: dict
) -> dict:
    """
    Determina la banda Fibonacci objetivo de menor grado para la recompra EREP (P2)
    según el nivel de compra original (P1).

    Regla del sistema:
    LONG:
      - P1 en o sobre LOWER_3 (-0.500 dev) -> P2 objetivo en LOWER_4 (-0.618 dev) o LOWER_5
      - P1 en LOWER_4 (-0.618 dev)        -> P2 objetivo en LOWER_5 (-0.764 dev) o LOWER_6
      - P1 en LOWER_5 (-0.764 dev)        -> P2 objetivo en LOWER_6 (-1.000 dev)
      - P1 en LOWER_6 (-1.000 dev)        -> No hay banda inferior; Stop Loss estructural final

    SHORT:
      - P1 en o bajo UPPER_3 (+0.500 dev) -> P2 objetivo en UPPER_4 (+0.618 dev) o UPPER_5
      - P1 en UPPER_4 (+0.618 dev)        -> P2 objetivo en UPPER_5 (+0.764 dev) o UPPER_6
      - P1 en UPPER_5 (+0.764 dev)        -> P2 objetivo en UPPER_6 (+1.000 dev)
      - P1 en UPPER_6 (+1.000 dev)        -> No hay banda superior; Stop Loss estructural final
    """
    snap = snap or {}
    is_long = str(side).lower() in ('long', 'buy')

    if is_long:
        l3 = float(snap.get('lower_3', 0))
        l4 = float(snap.get('lower_4', 0))
        l5 = float(snap.get('lower_5', 0))
        l6 = float(snap.get('lower_6', 0))

        if l3 <= 0 or l6 <= 0:
            return {
                'target_band': 'lower_4',
                'target_price': round(entry_price * 0.985, 6) if entry_price > 0 else 0.0,
                'reached': False,
                'is_climax_entry': False,
                'current_band': 'unknown'
            }

        if entry_price >= l3:
            current_band = 'above_or_at_lower_3'
            target_band = 'lower_4'
            target_price = l4
        elif entry_price >= l4:
            current_band = 'lower_4'
            target_band = 'lower_5'
            target_price = l5
        elif entry_price >= l5:
            current_band = 'lower_5'
            target_band = 'lower_6'
            target_price = l6
        else:
            current_band = 'lower_6_or_below'
            target_band = None
            target_price = 0.0

        reached = (target_price > 0 and current_price <= target_price)
        return {
            'target_band': target_band,
            'target_price': round(target_price, 6),
            'reached': reached,
            'is_climax_entry': (target_band is None),
            'current_band': current_band
        }
    else:
        u3 = float(snap.get('upper_3', 0))
        u4 = float(snap.get('upper_4', 0))
        u5 = float(snap.get('upper_5', 0))
        u6 = float(snap.get('upper_6', 0))

        if u3 <= 0 or u6 <= 0:
            return {
                'target_band': 'upper_4',
                'target_price': round(entry_price * 1.015, 6) if entry_price > 0 else 0.0,
                'reached': False,
                'is_climax_entry': False,
                'current_band': 'unknown'
            }

        if entry_price <= u3:
            current_band = 'below_or_at_upper_3'
            target_band = 'upper_4'
            target_price = u4
        elif entry_price <= u4:
            current_band = 'upper_4'
            target_band = 'upper_5'
            target_price = u5
        elif entry_price <= u5:
            current_band = 'upper_5'
            target_band = 'upper_6'
            target_price = u6
        else:
            current_band = 'upper_6_or_above'
            target_band = None
            target_price = 0.0

        reached = (target_price > 0 and current_price >= target_price)
        return {
            'target_band': target_band,
            'target_price': round(target_price, 6),
            'reached': reached,
            'is_climax_entry': (target_band is None),
            'current_band': current_band
        }


def find_target_fibonacci_band(
    snap:        dict,
    side:        str,
    current_price: float,
) -> dict:
    """
    Encuentra la banda Fibonacci inmediata en la dirección del recovery.
    """
    snap = snap or {}
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
    open_func = None,
    close_func = None,
) -> dict:
    """
    Ejecuta la acción determinada por evaluate_erep_phase().
    """
    if position.get('status') == 'closed':
        return {'executed': 'ignored_closed_position'}
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
        snap_act = action.get('snap') or {}
        atr_val = float(snap_act.get('atr', current_price * 0.015))
        if is_long:
            l6_val = float(snap_act.get('lower_6', 0))
            sl_struct = (l6_val - 1.2 * atr_val) if l6_val > 0 else (current_price * 0.985)
        else:
            u6_val = float(snap_act.get('upper_6', 0))
            sl_struct = (u6_val + 1.2 * atr_val) if u6_val > 0 else (current_price * 1.015)

        update_fields['sl_type'] = 'erep_structural_backstop'
        update_fields['stop_loss'] = round(sl_struct, 6)
        update_fields['sl_price'] = round(sl_struct, 6)

        supabase.table(table).update(update_fields).eq('id', pos_id).execute()
        position.update(update_fields)

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

        snap_act = action.get('snap') or {}
        atr_val = float(snap_act.get('atr', current_price * 0.015))
        if is_long:
            l6_val = float(snap_act.get('lower_6', 0))
            sl_struct = (l6_val - 1.2 * atr_val) if l6_val > 0 else (current_price * 0.985)
        else:
            u6_val = float(snap_act.get('upper_6', 0))
            sl_struct = (u6_val + 1.2 * atr_val) if u6_val > 0 else (current_price * 1.015)

        # Actualizar la posición original en memoria
        position['erep_phase'] = 3
        position['erep_p2_price'] = current_price
        position['erep_p2_size'] = p2_size
        position['erep_p3_avg'] = round(p3_avg, 6)
        position['sl_price'] = round(sl_struct, 6)
        position['stop_loss'] = round(sl_struct, 6)
        position['sl_type'] = 'erep_structural_backstop'

        # Actualizar la posición original en BD
        try:
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
                'sl_type':                'erep_structural_backstop',
                'stop_loss':              round(sl_struct, 6),
                'sl_price':               round(sl_struct, 6),
            }).eq('id', pos_id).execute()
        except Exception as upd_e:
            log_error('EREP', f"Error actualizando DB EREP P2 para {pos_id}: {upd_e}")

        # Notificar una sola vez por posición
        if pos_id not in _erep_p2_notified_set:
            _erep_p2_notified_set.add(pos_id)
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

    # ── MANTENER RUNNER A BANDA BOLLINGER (BLINDAJE SL EN P3) ──
    elif act == 'hold_runner_to_bb':
        new_sl = float(action.get('new_sl') or 0.0)
        p3_avg = float(action.get('p3_avg') or 0.0)
        target_bb = float(action.get('target_bb') or 0.0)

        position['sl_price'] = new_sl
        position['stop_loss'] = new_sl
        position['sl_type'] = 'erep_runner_be'
        position['erep_runner_active'] = True

        try:
            supabase.table(table).update({
                'sl_price': new_sl,
                'stop_loss': new_sl,
                'sl_type': 'erep_runner_be',
                'erep_runner_active': True,
            }).eq('id', pos_id).execute()
        except Exception as e:
            log_warning('EREP', f"Error blindando SL a Breakeven P3 para {pos_id}: {e}")

        runner_key = f"runner_{pos_id}"
        if runner_key not in _erep_p2_notified_set:
            _erep_p2_notified_set.add(runner_key)
            await send_telegram_local(
                f"🏃 EREP RUNNER BLINDADO [{symbol}] {side.upper()}\n"
                f"P3 Breakeven: ${p3_avg:.4f}\n"
                f"SL Blindado: ${new_sl:.4f} ($0.00 Riesgo)\n"
                f"Objetivo: Banda Bollinger ${target_bb:.4f}\n"
                f"🚀 Acompañando movimiento institucional!"
            )
        return {'executed': 'runner_retained', 'new_sl': new_sl}

    # ── CERRAR TODAS LAS POSICIONES ───────────
    elif act in ('close_all', 'close_sl', 'close_tp'):
        close_type = action.get('close_type', 'erep_close')
        if act == 'close_tp':
            close_type = 'recovery_success'
        elif act == 'close_sl':
            close_type = 'sl_normal'

        size = float(position.get('shares_remaining') or position.get('shares') or position.get('size') or 0.01)

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

        # Calcular P&L del EREP completo antes del update en BD
        p1_price = float(position.get('erep_p1_price') or position.get('entry_price', current_price))
        pnl_erep = (current_price - p1_price) / p1_price * 100 if p1_price > 0 else 0
        if str(side).lower() in ('short', 'sell'):
            pnl_erep = -pnl_erep
        pnl_usd = (pnl_erep / 100.0) * (p1_price * size)

        # Limpiar campos EREP en base de datos e incorporar campos de cierre principales con PnL calculado
        for attempt in range(max_retries):
            try:
                supabase.table(table).update({
                    'erep_active':       False,
                    'erep_phase':        0,
                    'erep_close_reason': close_type[:20],
                    'status':            'closed',
                    'closed_at':         datetime.now(timezone.utc).isoformat(),
                    'current_price':     current_price,
                    'close_reason':      f'EREP_{close_type.upper()}'[:20],
                    'realized_pnl':      round(pnl_usd, 4),
                    'realized_pnl_pct':  round(pnl_erep, 4)
                }).eq('id', pos_id).execute()
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    log_warning('EREP', f'Error P1 DB update attempt {attempt+1}: {e}. Retrying in 1s...')
                    await asyncio.sleep(1.0)
                else:
                    log_error('EREP', f'Error P1 DB update final: {e}')

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
