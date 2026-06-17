
"""
Sistema de Protección de Capital — 7 Reglas

Gestiona el ciclo de vida de una posición
para maximizar ganancias y minimizar pérdidas.

Compatible con:
  - Crypto: Binance Futures (BTC, ETH, SOL, ADA)
  - Forex:  IC Markets cTrader (EUR/USD, etc.)
  - Stocks: IB TWS (acciones US)
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict
from app.core.logger import log_info, log_error

# ── Configuración por mercado ─────────────────
PROTECTION_CONFIG = {
    'crypto_futures': {
        'be_trigger_pct':    0.012,  # +1.2%
        'be_buffer_pct':     0.002, # +0.2%
        'trailing_levels': [
            # (trigger_pct, new_sl_pct)
            (0.010,  0.002),   # +1.0% → SL a +0.2%
            (0.020,  0.008),   # +2.0% → SL a +0.8%
            (0.035,  0.015),   # +3.5% → SL a +1.5%
            (0.050,  0.025),   # +5.0% → SL a +2.5%
            (0.080,  0.040),   # +8.0% → SL a +4.0%
        ],
        'min_time_before_inverse_close': 2,
        # ciclos de 5m = 10 minutos
        'max_loss_before_inverse_close': 0.5,
        # cerrar por señal inversa solo si
        # pérdida < 50% del SL original
        'partial_close_tp1_pct':  0.008,  # +0.8%
        'partial_close_tp2_pct':  0.015,  # +1.5%
        'partial_close_ratio':    0.50,   # 50%
        'cooldown_cycles':        2,
        'counter_trend_size_pct': 0.50,
    },
    'forex_futures': {
        'be_trigger_pips':   8,
        'be_buffer_pips':    1,
        'trailing_levels_pips': [
            # (trigger_pips, new_sl_pips)
            (8,   1),    # +8 pips  → BE +1 pip
            (15,  5),    # +15 pips → SL a +5 pips
            (25,  12),   # +25 pips → SL a +12 pips
            (40,  25),   # +40 pips → SL a +25 pips
            (60,  40),   # +60 pips → SL a +40 pips
        ],
        'min_time_before_inverse_close': 3,
        # ciclos de 5m = 15 minutos
        'max_loss_before_inverse_close': 0.5,
        'partial_close_tp1_pips':  20,
        'partial_close_tp2_pips':  40,
        'partial_close_ratio':     0.50,
        'cooldown_cycles':         3,
        'counter_trend_size_pct':  0.50,
    },
    'stocks_spot': {
        'be_trigger_pct':    0.005,  # +0.5%
        'be_buffer_pct':     0.001,  # +0.1%
        'trailing_levels': [
            (0.005,  0.001),   # +0.5% → +0.1%
            (0.010,  0.004),   # +1.0% → +0.4%
            (0.020,  0.010),   # +2.0% → +1.0%
            (0.035,  0.020),   # +3.5% → +2.0%
            (0.050,  0.030),   # +5.0% → +3.0%
        ],
        'min_time_before_inverse_close': 4,
        'max_loss_before_inverse_close': 0.5,
        'partial_close_tp1_pct':  0.015,  # +1.5%
        'partial_close_tp2_pct':  0.030,  # +3.0%
        'partial_close_ratio':    0.50,
        'cooldown_cycles':        2,
        'counter_trend_size_pct': 0.50,
    },
}

# Pip sizes para Forex
PIP_SIZES = {
    'EURUSD': 0.0001, 'GBPUSD': 0.0001,
    'USDJPY': 0.01,   'USDCHF': 0.0001,
    'XAUUSD': 0.01,   'AUDUSD': 0.0001,
}

# Configuración de trailing dinámico por símbolo
VOLATILE_TRAILING_CONFIG = {
    'XAUUSD': {
        'pip_size':             0.01,
        'min_pips_to_activate': 3,

        # ── Parámetros LONG ───────────────────
        'long': {
            'phase1_atr_mult':      1.5,
            'candle_switch_pips':   10,
            'candle_lookback':       2,
            'candle_timeframe':     '15m',
            'accel_switch_pips':    25,
            'accel_atr_mult':        0.8,
        },

        # ── Parámetros SHORT ──────────────────
        'short': {
            'phase1_atr_mult':      1.3,
            'candle_switch_pips':   8,
            'candle_lookback':      2,
            'candle_timeframe':     '5m',
            'accel_switch_pips':    18,
            'accel_atr_mult':       0.7,
            'accel_atr_mult_5m':    0.6,
        },

        # ── Parámetros compartidos ────────────
        'asia_session_mult_adj':    0.7,
        'mtf_entry_min':            0.20,
        'atr_ratio_calm':           1.0,
        'atr_ratio_volatile':       1.5,
        'atr_mult_calm_adj':        1.3,
        'atr_mult_volatile_adj':    1.0,
    },

    'GBPUSD': {
        'pip_size':             0.0001,
        'min_pips_to_activate': 3,
        'long': {
            'phase1_atr_mult':      1.4,
            'candle_switch_pips':   8,
            'candle_lookback':      2,
            'candle_timeframe':     '15m',
            'accel_switch_pips':    20,
            'accel_atr_mult':       0.7,
        },
        'short': {
            'phase1_atr_mult':      1.2,
            'candle_switch_pips':   6,
            'candle_lookback':      2,
            'candle_timeframe':     '5m',
            'accel_switch_pips':    15,
            'accel_atr_mult':       0.65,
            'accel_atr_mult_5m':    0.55,
        },
        'asia_session_mult_adj':    0.8,
        'mtf_entry_min':            0.15,
        'atr_ratio_calm':           1.0,
        'atr_ratio_volatile':       1.5,
        'atr_mult_calm_adj':        1.2,
        'atr_mult_volatile_adj':    0.9,
    },

    'EURUSD': {
        'pip_size':             0.0001,
        'min_pips_to_activate': 2,
        'long': {
            'phase1_atr_mult':      1.3,
            'candle_switch_pips':   7,
            'candle_lookback':      2,
            'candle_timeframe':     '15m',
            'accel_switch_pips':    18,
            'accel_atr_mult':       0.7,
        },
        'short': {
            'phase1_atr_mult':      1.1,
            'candle_switch_pips':   5,
            'candle_lookback':      2,
            'candle_timeframe':     '5m',
            'accel_switch_pips':    14,
            'accel_atr_mult':       0.65,
            'accel_atr_mult_5m':    0.55,
        },
        'asia_session_mult_adj':    0.8,
        'mtf_entry_min':            0.10,
        'atr_ratio_calm':           1.0,
        'atr_ratio_volatile':       1.5,
        'atr_mult_calm_adj':        1.2,
        'atr_mult_volatile_adj':    0.9,
    },

    'USDJPY': {
        'pip_size':             0.01,
        'min_pips_to_activate': 2,
        'long': {
            'phase1_atr_mult':      1.3,
            'candle_switch_pips':   7,
            'candle_lookback':      2,
            'candle_timeframe':     '15m',
            'accel_switch_pips':    18,
            'accel_atr_mult':       0.7,
        },
        'short': {
            'phase1_atr_mult':      1.1,
            'candle_switch_pips':   5,
            'candle_lookback':      2,
            'candle_timeframe':     '5m',
            'accel_switch_pips':    14,
            'accel_atr_mult':       0.65,
            'accel_atr_mult_5m':    0.55,
        },
        'asia_session_mult_adj':    1.0,
        'mtf_entry_min':            0.10,
        'atr_ratio_calm':           1.0,
        'atr_ratio_volatile':       1.5,
        'atr_mult_calm_adj':        1.2,
        'atr_mult_volatile_adj':    0.9,
    },
}

FOREX_SESSIONS = {
    'asia':   (0,  8),
    'london': (7,  16),
    'new_york': (12, 21),
}

def get_current_session() -> str:
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    if 12 <= hour < 21:
        return 'new_york'
    elif 7 <= hour < 16:
        return 'london'
    else:
        return 'asia'

def get_atr_current(
    df_15m:    pd.DataFrame,
    period:    int = 14,
    avg_period: int = 50,
) -> dict:
    if df_15m is None or len(df_15m) < max(period, avg_period):
        return {
            'atr':   0.0,
            'avg':   0.0,
            'ratio': 1.0,
            'regime': 'normal',
        }

    df = df_15m.copy()
    df['pc']  = df['close'].shift(1)
    df['tr']  = df.apply(
        lambda r: max(
            r['high'] - r['low'],
            abs(r['high'] - (r['pc'] or r['close'])),
            abs(r['low']  - (r['pc'] or r['close']))
        ), axis=1
    )

    atr_now = float(df['tr'].tail(period).mean())
    atr_avg = float(df['tr'].tail(avg_period).mean())
    ratio   = atr_now / atr_avg if atr_avg > 0 else 1.0

    return {
        'atr':   round(atr_now, 6),
        'avg':   round(atr_avg, 6),
        'ratio': round(ratio, 3),
        'regime': (
            'calm'    if ratio < 1.0 else
            'volatile' if ratio > 1.5 else
            'normal'
        ),
    }

def get_atr_5m(
    df_5m:      pd.DataFrame,
    period:     int = 14,
    avg_period: int = 50,
) -> dict:
    """
    Calcula el ATR en temporaridad de 5m.
    Más sensible a la volatilidad inmediata que el ATR de 15m.
    """
    if df_5m is None or len(df_5m) < period:
        return {
            'atr':    0.0,
            'avg':    0.0,
            'ratio':  1.0,
            'regime': 'normal',
        }

    df     = df_5m.copy()
    df['pc'] = df['close'].shift(1)
    df['tr'] = df.apply(
        lambda r: max(
            r['high'] - r['low'],
            abs(r['high'] - (r['pc'] if pd.notna(r['pc']) else r['close'])),
            abs(r['low']  - (r['pc'] if pd.notna(r['pc']) else r['close']))
        ), axis=1
    )

    atr_now = float(df['tr'].tail(period).mean())
    atr_avg = float(
        df['tr'].tail(avg_period).mean()
    ) if len(df) >= avg_period else atr_now

    ratio = atr_now / atr_avg if atr_avg > 0 else 1.0

    return {
        'atr':    round(atr_now, 6),
        'avg':    round(atr_avg, 6),
        'ratio':  round(ratio, 3),
        'regime': (
            'calm'     if ratio < 0.8 else
            'volatile' if ratio > 1.4 else
            'normal'
        ),
    }

def get_candle_sl_short_5m(
    df_5m:     pd.DataFrame,
    side:      str,
    lookback:  int = 2,
) -> dict:
    """
    Para SHORT/SELL en 5m: SL = max(HIGH de las últimas N velas de 5m)
    Para LONG/BUY en 5m: SL = min(LOW de las últimas N velas de 5m)
    """
    if df_5m is None or len(df_5m) < lookback + 1:
        return {
            'sl_price':    None,
            'valid':       False,
            'candles_used': 0,
            'reason':      'Datos insuficientes en 5m',
        }

    # Excluir la vela vigente (última). Solo usar velas YA CERRADAS
    closed = df_5m.iloc[-(lookback + 1):-1]

    if side in ('short', 'sell'):
        # Para SHORT: SL en el máximo de los highs
        sl_price = float(closed['high'].max())
        desc     = f'Max high de {lookback} velas cerradas (5m): {sl_price:.5f}'
    else:
        # Para LONG en 5m
        sl_price = float(closed['low'].min())
        desc     = f'Min low de {lookback} velas cerradas (5m): {sl_price:.5f}'

    return {
        'sl_price':     round(sl_price, 6),
        'valid':        True,
        'lookback':     lookback,
        'candles_used': len(closed),
        'timeframe':    '5m',
        'reason':       desc,
    }

def evaluate_volatile_trailing(
    symbol:        str,
    side:          str,
    entry_price:   float,
    current_price: float,
    highest_price: float,
    current_sl:    float,
    df_15m:        pd.DataFrame,
    atr_snap:      float = 0,
    df_5m:         pd.DataFrame = None,
) -> dict:
    cfg = VOLATILE_TRAILING_CONFIG.get(symbol)
    if not cfg:
        return {'action': 'none', 'reason': 'Sin config dinámica'}

    pip      = cfg['pip_size']
    min_pips = cfg['min_pips_to_activate']

    if side in ('long', 'buy'):
        pnl_pips  = (current_price - entry_price) / pip
        max_price = max(highest_price, current_price)
    else:
        pnl_pips  = (entry_price - current_price) / pip
        max_price = min(highest_price, current_price)

    if pnl_pips < min_pips:
        return {
            'action':   'none',
            'pnl_pips': round(pnl_pips, 1),
            'reason': f'Ganancia {pnl_pips:.1f} pips < mínimo {min_pips} pips',
        }

    atr_data = get_atr_current(df_15m)
    atr      = atr_data['atr'] if atr_data['atr'] > 0 else atr_snap
    if atr <= 0:
        atr = pip * 5

    regime = atr_data['regime']
    if regime == 'calm':
        mult_adj = cfg['atr_mult_calm_adj']
    elif regime == 'volatile':
        mult_adj = cfg['atr_mult_volatile_adj']
    else:
        mult_adj = 1.0

    session = get_current_session()
    if session == 'asia':
        sess_adj = cfg['asia_session_mult_adj']
    else:
        sess_adj = 1.0

    phase1_mult = cfg['phase1_atr_mult'] * mult_adj * sess_adj
    atr_dist    = atr * phase1_mult

    if side in ('long', 'buy'):
        sl_phase1 = max_price - atr_dist
    else:
        sl_phase1 = max_price + atr_dist

    active_phase = 1
    sl_phases    = {'phase1': round(sl_phase1, 6)}

    sl_phase2    = None
    candle_pips  = cfg['candle_switch_pips']
    lookback     = cfg['candle_lookback']

    # PREFER 5m candles for Phase 2 (faster reaction to volatility)
    fast_df = df_5m if df_5m is not None else df_15m
    
    if pnl_pips >= candle_pips and fast_df is not None and len(fast_df) >= lookback + 1:
        closed = fast_df.iloc[-(lookback+1):-1]
        if side in ('long', 'buy'):
            sl_phase2 = float(closed['low'].min())
        else:
            sl_phase2 = float(closed['high'].max())
        sl_phases['phase2'] = round(sl_phase2, 6)

    sl_phase3    = None
    accel_pips   = cfg['accel_switch_pips']
    accel_mult   = cfg['accel_atr_mult'] * sess_adj

    if pnl_pips >= accel_pips:
        accel_dist = atr * accel_mult
        if side in ('long', 'buy'):
            sl_phase3 = current_price - accel_dist
        else:
            sl_phase3 = current_price + accel_dist
        sl_phases['phase3'] = round(sl_phase3, 6)

    candidates = [sl_phase1]
    if sl_phase2 is not None: candidates.append(sl_phase2)
    if sl_phase3 is not None: candidates.append(sl_phase3)

    if side in ('long', 'buy'):
        best_sl = max(candidates)
        final_sl = max(best_sl, current_sl)
        final_sl = min(final_sl, current_price - (pip * 2))
    else:
        best_sl = min(candidates)
        final_sl = min(best_sl, current_sl)
        final_sl = max(final_sl, current_price + (pip * 2))

    final_sl = round(final_sl, 6)

    if sl_phase3 is not None and abs(final_sl - sl_phase3) < pip:
        active_phase = 3
    elif sl_phase2 is not None and abs(final_sl - sl_phase2) < pip:
        active_phase = 2
    else:
        active_phase = 1

    improved = (
        (side in ('long','buy') and final_sl > current_sl + pip) or
        (side not in ('long','buy') and final_sl < current_sl - pip)
    )

    dist_pips = abs(current_price - final_sl) / pip

    return {
        'action':       'update_sl' if improved else 'none',
        'sl_price':     final_sl,
        'active_phase': active_phase,
        'sl_phases':    sl_phases,
        'improved':     improved,
        'pnl_pips':     round(pnl_pips, 1),
        'dist_pips':    round(dist_pips, 1),
        'atr':          round(atr, 6),
        'regime':       regime,
        'session':      session,
        'mult_used':    round(phase1_mult, 3),
        'reason': (
            f'Trail dinámico {symbol} [Fase {active_phase}]: '
            f'SL={final_sl:.5f} ({dist_pips:.1f} pips). '
            f'PnL=+{pnl_pips:.1f} pips. Régimen={regime}. Sesión={session}. '
            f'ATR×{phase1_mult:.2f}={atr_dist/pip:.1f}pips'
        ),
    }

def evaluate_volatile_trailing_v2(
    symbol:        str,
    side:          str,
    entry_price:   float,
    current_price: float,
    best_price:    float,
    # LONG: precio máximo alcanzado. SHORT: precio mínimo alcanzado
    current_sl:    float,
    df_15m:        pd.DataFrame,
    df_5m:         pd.DataFrame = None,
    atr_snap:      float = 0,
) -> dict:
    """
    Trailing Stop Dinámico v2. Compatible con LONG y SHORT.
    Usa exclusivamente velas de 15m para evitar ruido y retrocesos rápidos de 5m.
    """
    cfg_sym = VOLATILE_TRAILING_CONFIG.get(symbol)
    if not cfg_sym:
        return {'action': 'none', 'reason': f'{symbol} sin config dinámica'}

    is_long  = side in ('long', 'buy')
    is_short = not is_long

    # Seleccionar configuración por dirección
    dir_cfg = cfg_sym.get('long' if is_long else 'short', {})
    pip          = cfg_sym['pip_size']
    min_pips     = cfg_sym['min_pips_to_activate']
    candle_tf    = '15m' # Forzado a 15m

    # ── P&L actual en pips ────────────────────
    if is_long:
        pnl_pips = (current_price - entry_price) / pip
    else:
        pnl_pips = (entry_price - current_price) / pip

    if pnl_pips < min_pips:
        return {
            'action':   'none',
            'side':     side,
            'pnl_pips': round(pnl_pips, 1),
            'reason': f'Ganancia {pnl_pips:.1f} pips < mínimo {min_pips} pips',
        }

    # ── ATR según temporaridad (siempre 15m) ──
    atr_data = get_atr_current(df_15m)

    atr    = atr_data['atr'] if atr_data['atr'] > 0 else atr_snap
    if atr <= 0:
        atr = pip * 4  # fallback

    # ── Ajuste por régimen y sesión ───────────
    regime   = atr_data.get('regime', 'normal')
    session  = get_current_session()

    if regime == 'calm':
        mult_adj = cfg_sym['atr_mult_calm_adj']
    elif regime == 'volatile':
        mult_adj = cfg_sym['atr_mult_volatile_adj']
    else:
        mult_adj = 1.0

    if session == 'asia':
        sess_adj = cfg_sym['asia_session_mult_adj']
    else:
        sess_adj = 1.0

    # ── FASE 1: ATR Chandelier ────────────────
    phase1_mult = dir_cfg.get('phase1_atr_mult', 1.3) * mult_adj * sess_adj
    atr_dist = atr * phase1_mult

    if is_long:
        sl_phase1 = best_price - atr_dist
    else:
        sl_phase1 = best_price + atr_dist

    phases = {'phase1': round(sl_phase1, 6)}

    # ── FASE 2: Velas (siempre 15m) ───────────
    sl_phase2         = None
    candle_pips_thr   = dir_cfg.get('candle_switch_pips', 8)
    candle_lookback   = dir_cfg.get('candle_lookback', 2)

    if pnl_pips >= candle_pips_thr:
        # Usar siempre velas estables de 15m
        candle_data = get_candle_sl_short_5m(df_15m, side, candle_lookback)

        if candle_data['valid']:
            sl_phase2 = candle_data['sl_price']
            phases['phase2'] = round(sl_phase2, 6)

    # ── FASE 3: Aceleración ───────────────────
    sl_phase3       = None
    accel_pips_thr  = dir_cfg.get('accel_switch_pips', 18)

    # Para SHORT en 5m: usar accel_atr_mult_5m
    if is_short and '5m' in candle_tf:
        accel_mult = dir_cfg.get('accel_atr_mult_5m', dir_cfg.get('accel_atr_mult', 0.65))
    else:
        accel_mult = dir_cfg.get('accel_atr_mult', 0.7)
    accel_mult *= sess_adj

    if pnl_pips >= accel_pips_thr:
        accel_dist = atr * accel_mult
        if is_long:
            sl_phase3 = current_price - accel_dist
        else:
            sl_phase3 = current_price + accel_dist
        phases['phase3'] = round(sl_phase3, 6)

    # ── Elegir el mejor SL ────────────────────
    candidates = [sl_phase1]
    if sl_phase2 is not None:
        candidates.append(sl_phase2)
    if sl_phase3 is not None:
        candidates.append(sl_phase3)

    # ── FASE 4: Optimización Avanzada SIPV (Lógica de Velas en Vivo) ──
    sl_phase4 = None
    pine_signal = ''
    if df_15m is not None and len(df_15m) > 0:
        pine_signal = str(df_15m.iloc[-1].get('pinescript_signal', ''))
        
    bb_touch = False
    if df_15m is not None and len(df_15m) >= 2:
        c0 = df_15m.iloc[-1]
        c1 = df_15m.iloc[-2]
        
        c0_high, c0_low = float(c0.get('high', 0)), float(c0.get('low', 0))
        c0_open, c0_close = float(c0.get('open', 0)), float(c0.get('close', 0))
        c1_open, c1_close = float(c1.get('open', 0)), float(c1.get('close', 0))
        
        bb_upper = float(c0.get('upper_2', 0))
        bb_lower = float(c0.get('lower_2', 0))
        
        if is_long:
            bb_touch = (c0_high >= bb_upper) if bb_upper > 0 else False
            pine_trigger = (pine_signal == 'Sell')
        else:
            bb_touch = (c0_low <= bb_lower) if bb_lower > 0 else False
            pine_trigger = (pine_signal == 'Buy')
            
        if bb_touch or pine_trigger:
            c1_body = abs(c1_close - c1_open)
            buffer = c1_body * 0.03
            
            if is_long:
                if c1_close > c1_open: # C1 verde
                    if c0_open >= c1_close:
                        # Escenario A
                        sl_phase4 = c1_close - buffer
                    else:
                        # Escenario B
                        sl_phase4 = c1_open
                else: # C1 roja
                    # Escenario C
                    if pine_trigger and pnl_pips > 0:
                        sl_phase4 = current_price - (pip * 1.5)
            else: # is_short
                if c1_close < c1_open: # C1 roja
                    if c0_open <= c1_close:
                        # Escenario A
                        sl_phase4 = c1_close + buffer
                    else:
                        # Escenario B
                        sl_phase4 = c1_open
                else: # C1 verde
                    # Escenario C
                    if pine_trigger and pnl_pips > 0:
                        sl_phase4 = current_price + (pip * 1.5)
                        
            if sl_phase4 is not None:
                candidates.append(sl_phase4)
                phases['phase4_sipv'] = round(sl_phase4, 6)

    if is_long:
        # LONG: SL más ALTO = mayor protección
        best_sl  = max(candidates)
        final_sl = max(best_sl, current_sl)
        # Nunca superar el precio actual
        final_sl = min(final_sl, current_price - (pip * 2))
    else:
        # SHORT: SL más BAJO = mayor protección
        best_sl  = min(candidates)
        final_sl = min(best_sl, current_sl)
        # Nunca bajar del precio actual
        final_sl = max(final_sl, current_price + (pip * 2))

    final_sl = round(final_sl, 6)

    # ── Fase activa ───────────────────────────
    tol = pip * 0.5
    if sl_phase4 is not None and abs(final_sl - sl_phase4) <= tol:
        active_phase = 4
    elif sl_phase3 is not None and abs(final_sl - sl_phase3) <= tol:
        active_phase = 3
    elif sl_phase2 is not None and abs(final_sl - sl_phase2) <= tol:
        active_phase = 2
    else:
        active_phase = 1

    # ── ¿Mejoró el SL? ───────────────────────
    improved = (
        (is_long  and final_sl > current_sl + pip) or
        (is_short and final_sl < current_sl - pip)
    )

    dist_pips = abs(current_price - final_sl) / pip

    return {
        'action':       'update_sl' if improved else 'none',
        'sl_price':     final_sl,
        'active_phase': active_phase,
        'phases':       phases,
        'improved':     improved,
        'pnl_pips':     round(pnl_pips, 1),
        'dist_pips':    round(dist_pips, 1),
        'atr':          round(atr, 6),
        'regime':       regime,
        'session':      session,
        'timeframe':    candle_tf,
        'side':         side,
        'reason': (
            f'Trail {side.upper()} {symbol} [Fase {active_phase}/{candle_tf}]: '
            f'SL={final_sl:.5f} ({dist_pips:.1f} pips del precio). '
            f'PnL=+{pnl_pips:.1f} pips. ATR×{phase1_mult:.2f}. '
            f'Régimen={regime}. Sesión={session}'
        ),
    }

@dataclass
class ProtectionState:
    """
    Estado de protección de una posición.
    Se almacena en memory y opcionalmente se persiste.
    """
    position_id:       str
    symbol:            str
    side:              str
    entry_price:       float
    current_sl:        float
    original_sl:       float
    market_type:       str
    rule_code:         str = ''

    # Trailing
    # Trailing
    trailing_level:    int   = 0
    highest_pnl_pct:   float = 0.0

    # LONG: precio más alto alcanzado
    highest_price:      float = 0.0
    # SHORT: precio más bajo alcanzado ← NUEVO
    lowest_price:       float = 0.0

    bb_touched:         bool  = False

    be_activated:       bool  = False
    be_price:           float = 0.0

    partial_closed:     bool  = False
    partial_size:       float = 0.0
    remaining_size:     float = 0.0

    cycles_open:        int   = 0
    last_close_cycle:   int   = 0
    inverse_signal_cycles: int = 0

    # NUEVO: para trailing dinámico SHORT
    lowest_sl_achieved: float = 0.0
    # El SL más ceñido que hemos logrado
    # (para SHORT: el valor más ALTO del SL mientras el precio bajaba)
    phase_history:      list  = field(default_factory=list)
    # Historial de fases del trailing
    opened_at:          str   = ''


def calculate_pnl(
    entry:   float,
    current: float,
    side:    str,
    symbol:  str = '',
    market_type: str = 'crypto_futures'
) -> dict:
    """Calcula el P&L en % y en pips."""
    if entry <= 0:
        return {'pct': 0.0, 'pips': 0.0, 'is_profit': False}

    is_long = side.lower() in ('long', 'buy')
    if is_long:
        pct  = (current - entry) / entry * 100
        diff = current - entry
    else:
        pct  = (entry - current) / entry * 100
        diff = entry - current

    pips = 0.0
    if market_type == 'forex_futures':
        pip = PIP_SIZES.get(symbol, 0.0001)
        pips = diff / pip

    return {
        'pct':       round(pct,  4),
        'pips':      round(pips, 1),
        'diff':      round(diff, 6),
        'is_profit': pct > 0,
    }


def evaluate_trailing_stop(
    state:         ProtectionState,
    current_price: float,
    df_15m:        pd.DataFrame = None,
    snap:          dict = None,
    df_5m:         pd.DataFrame = None,
) -> dict:
    """
    REGLA 4: Trailing Stop Escalonado.
    Evalúa si el SL debe subir al siguiente nivel. El SL NUNCA retrocede.
    """
    symbol = state.symbol
    is_long = state.side.lower() in ('long', 'buy')

    # ── FALLBACK 5M PROTECTION ──
    if df_15m is not None and len(df_15m) >= 20 and df_5m is not None and len(df_5m) >= 20:
        try:
            has_profit = (current_price > state.entry_price) if is_long else (current_price < state.entry_price)
            if has_profit:
                df15 = df_15m.copy()
                ema3_15 = float(df15['close'].ewm(span=3, adjust=False).mean().iloc[-1])
                ema9_15 = float(df15['close'].ewm(span=9, adjust=False).mean().iloc[-1])
                ema20_15 = float(df15['close'].ewm(span=20, adjust=False).mean().iloc[-1])
                
                df5 = df_5m.copy()
                ema3_5 = float(df5['close'].ewm(span=3, adjust=False).mean().iloc[-1])
                ema9_5 = float(df5['close'].ewm(span=9, adjust=False).mean().iloc[-1])
                ema20_5 = float(df5['close'].ewm(span=20, adjust=False).mean().iloc[-1])
                close_5 = float(df5['close'].iloc[-1])
                
                if is_long:
                    # 15m adverse or weak (EMA3 < EMA9 or EMA9 < EMA20)
                    if ema3_15 < ema9_15 or ema9_15 < ema20_15:
                        # 5m bullish micro-impulse (EMA3 > EMA9 > EMA20)
                        if ema3_5 > ema9_5 and ema9_5 > ema20_5:
                            # 5m close below EMA3
                            if close_5 < ema3_5:
                                return {'action': 'close_market', 'reason': 'Fallback_5m_EMA3_close', 'new_level': 99}
                else:
                    # 15m adverse or weak (EMA3 > EMA9 or EMA9 > EMA20)
                    if ema3_15 > ema9_15 or ema9_15 > ema20_15:
                        # 5m bearish micro-impulse (EMA3 < EMA9 < EMA20)
                        if ema3_5 < ema9_5 and ema9_5 < ema20_5:
                            # 5m close above EMA3
                            if close_5 > ema3_5:
                                return {'action': 'close_market', 'reason': 'Fallback_5m_EMA3_close', 'new_level': 99}
        except Exception as e:
            from app.core.logger import log_error
            log_error('FALLBACK_5M', f"Error evaluando protección 5m para {symbol}: {e}")
    # ── CUSTOM DYNAMIC TRAILING: ApexConfluence ──
    rule_code = getattr(state, 'rule_code', '')
    if rule_code == 'ApexConfluence' and df_15m is not None and len(df_15m) >= 20:
        df = df_15m.copy()
        df['ema3'] = df['close'].ewm(span=3, adjust=False).mean()
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean() if len(df) >= 200 else df['ema20']
        
        std20 = df['close'].rolling(20).std()
        df['bb_upper'] = df['ema20'] + (std20 * 2)
        df['bb_lower'] = df['ema20'] - (std20 * 2)
        
        last_row = df.iloc[-1]
        
        # 🛡️ Cierre de vela candle-close guard (Bypass pre-opening/historical candles)
        opened_at_str = getattr(state, 'opened_at', '')
        if opened_at_str and 'open_time' in last_row:
            try:
                opened_at = pd.to_datetime(opened_at_str).tz_localize(None)
                candle_open = pd.to_datetime(last_row['open_time']).tz_localize(None)
                # La vela se considera cerrada 15 minutos después de su open_time
                candle_close = candle_open + pd.Timedelta(minutes=15)
                
                if candle_close <= opened_at:
                    # La vela evaluada cerró antes o en el mismo momento de abrir la posición
                    # Retornamos none para evitar cierres inmediatos por velas pre-apertura
                    return {'action': 'none', 'reason': 'Esperando primer cierre de vela de 15m.'}
            except Exception as timestamp_err:
                log_error('TRAILING_CANDLE_GUARD', f"Error validando tiempo de cierre de vela: {timestamp_err}")
                
        close_price = float(last_row['close'])
        open_price = float(last_row['open'])
        ema3 = float(last_row['ema3'])
        ema9 = float(last_row['ema9'])
        ema20 = float(last_row['ema20'])
        ema50 = float(last_row['ema50'])
        ema200 = float(last_row['ema200'])
        bb_upper = float(last_row['bb_upper'])
        bb_lower = float(last_row['bb_lower'])
        upper_6 = float(last_row.get('upper_6', 0))
        lower_6 = float(last_row.get('lower_6', 0))
        
        is_long = state.side.lower() in ('long', 'buy')
        
        if is_long:
            confluence_active = (ema3 > ema9) and (ema9 >= ema20)
        else:
            confluence_active = (ema3 < ema9) and (ema9 <= ema20)
            
        if confluence_active:
            bb_touched = getattr(state, 'bb_touched', False)
            touched_now = False
            if is_long:
                if close_price >= bb_upper and not bb_touched:
                    state.bb_touched = True
                    bb_touched = True
                    touched_now = True
            else:
                if close_price <= bb_lower and not bb_touched:
                    state.bb_touched = True
                    bb_touched = True
                    touched_now = True
                    
            action_dict = {'action': 'none'}
            
            if is_long:
                # 1) Move SL on green candles to EMA3, and TP to UPPER_6
                if close_price > open_price:
                    if state.current_sl == 0 or ema3 > state.current_sl:
                        action_dict = {
                            'action': 'update_sl',
                            'new_sl': ema3,
                            'reason': 'ApexConfluence_green_candle_trail',
                            'new_level': 1
                        }
                        if upper_6 > 0:
                            action_dict['new_tp'] = upper_6
                # 2) Close position if red candle closes below EMA3
                elif close_price < open_price:
                    if close_price < ema3:
                        action_dict = {
                            'action': 'close_market',
                            'reason': 'ApexConfluence_ema3_close',
                            'bb_touched': bb_touched
                        }
            else:
                # 1) Move SL on red candles to EMA3, and TP to LOWER_6
                if close_price < open_price:
                    if state.current_sl == 0 or ema3 < state.current_sl:
                        action_dict = {
                            'action': 'update_sl',
                            'new_sl': ema3,
                            'reason': 'ApexConfluence_red_candle_trail',
                            'new_level': 1
                        }
                        if lower_6 > 0:
                            action_dict['new_tp'] = lower_6
                # 2) Close position if green candle closes above EMA3
                elif close_price > open_price:
                    if close_price > ema3:
                        action_dict = {
                            'action': 'close_market',
                            'reason': 'ApexConfluence_ema3_close',
                            'bb_touched': bb_touched
                        }
                        
            if touched_now:
                if action_dict['action'] == 'none':
                    action_dict = {
                        'action': 'update_bb_touched',
                        'bb_touched': True
                    }
                else:
                    action_dict['update_bb_touched'] = True
                    
            return action_dict

    # ── CUSTOM TRAILING FOR STRATEGY ApexEma (SwingEma) ──
    if rule_code in ('AaApexEma', 'BbApexEma', 'AaHot', 'BbHot'):
        if df_15m is not None and len(df_15m) >= 20:
            df = df_15m.copy()
            df['ema3'] = df['close'].ewm(span=3, adjust=False).mean()
            
            # Vela cerrada más reciente
            last_row = df.iloc[-1]
            close_price = float(last_row['close'])
            open_price = float(last_row['open'])
            ema3 = float(last_row['ema3'])
            
            is_long = state.side.lower() in ('long', 'buy')
            
            if is_long:
                # LONG: vela verde (close > open) y close > ema3
                if close_price > open_price and close_price > ema3:
                    if state.current_sl == 0 or ema3 > state.current_sl:
                        return {
                            'action': 'update_sl',
                            'new_sl': ema3,
                            'reason': 'swing_ema_green_candle_trail',
                            'new_level': 1
                        }
            else:
                # SHORT: vela roja (close < open) y close < ema3
                if close_price < open_price and close_price < ema3:
                    if state.current_sl == 0 or ema3 < state.current_sl:
                        return {
                            'action': 'update_sl',
                            'new_sl': ema3,
                            'reason': 'swing_ema_red_candle_trail',
                            'new_level': 1
                        }
        return {'action': 'none'}

    # ── Símbolos con trailing dinámico ────────
    if symbol in VOLATILE_TRAILING_CONFIG and state.market_type == 'forex_futures':
        atr_snap = float(snap.get('atr') if snap.get('atr') is not None else 0) if snap else 0
        
        # best_price: máximo para LONG, mínimo para SHORT
        if state.side in ('long', 'buy'):
            best_price = max(state.highest_price, state.entry_price)
        else:
            best_price = state.lowest_price if state.lowest_price > 0 else state.entry_price

        result = evaluate_volatile_trailing_v2(
            symbol        = symbol,
            side          = state.side,
            entry_price   = state.entry_price,
            current_price = current_price,
            best_price    = best_price,
            current_sl    = state.current_sl,
            df_15m        = df_15m,
            df_5m         = df_5m,
            atr_snap      = atr_snap,
        )

        if result['action'] == 'update_sl':
            state.current_sl = result['sl_price']
            # Actualizar marcas históricas
            if state.side in ('long', 'buy'):
                state.highest_price = max(state.highest_price, current_price)
            else:
                state.lowest_price = min(state.lowest_price if state.lowest_price > 0 else current_price, current_price)
            
            return {
                'action':     'update_sl',
                'new_sl':     result['sl_price'],
                'new_level':  result['active_phase'],
                'trigger':    f'+{result["pnl_pips"]:.1f} pips',
                'reason':     result['reason'],
                'dynamic':    True,
                'phase':      result['active_phase'],
                'dist_pips':  result['dist_pips'],
                'timeframe':  result.get('timeframe', '15m')
            }

        return {
            'action': 'none',
            'reason': result['reason'],
        }

    # ── Trailing escalónado original ──────────
    cfg  = PROTECTION_CONFIG.get(state.market_type, {})
    side = state.side.lower()
    is_long = side in ('long', 'buy')
    entry = state.entry_price

    pnl = calculate_pnl(entry, current_price, side, state.symbol, state.market_type)

    if state.market_type == 'forex_futures':
        current_gain = pnl['pips']
        levels       = cfg.get('trailing_levels_pips', [])
        pip = PIP_SIZES.get(state.symbol, 0.0001)

        for i, (trigger, new_sl_pips) in enumerate(levels):
            level_idx = i + 1
            if current_gain >= trigger and state.trailing_level < level_idx:
                if is_long:
                    new_sl = entry + (new_sl_pips * pip)
                else:
                    new_sl = entry - (new_sl_pips * pip)

                # Verificar que el nuevo SL es mejor (nunca retrocede)
                if is_long:
                    if new_sl <= state.current_sl: continue
                else:
                    if new_sl >= state.current_sl: continue

                return {
                    'action':    'update_sl',
                    'new_sl':    round(new_sl, 6),
                    'new_level': level_idx,
                    'reason': (
                        f'Trailing nivel {level_idx}: '
                        f'+{trigger} pips alcanzados → SL a +{new_sl_pips} pips ({new_sl:.6f})'
                    ),
                }
    else:  # crypto / stocks
        current_gain = pnl['pct'] / 100
        levels       = cfg.get('trailing_levels', [])

        # ── SIPV Override for Crypto ──
        sl_sipv = None
        pine_signal = ''
        if df_15m is not None and len(df_15m) > 0:
            pine_signal = str(df_15m.iloc[-1].get('pinescript_signal', ''))
            
        bb_touch = False
        if df_15m is not None and len(df_15m) >= 2:
            c0 = df_15m.iloc[-1]
            c1 = df_15m.iloc[-2]
            
            c0_high, c0_low = float(c0.get('high', 0)), float(c0.get('low', 0))
            c0_open, c0_close = float(c0.get('open', 0)), float(c0.get('close', 0))
            c1_open, c1_close = float(c1.get('open', 0)), float(c1.get('close', 0))
            
            bb_upper = float(c0.get('upper_2', 0))
            bb_lower = float(c0.get('lower_2', 0))
            
            if is_long:
                bb_touch = (c0_high >= bb_upper) if bb_upper > 0 else False
                pine_trigger = (pine_signal == 'Sell')
            else:
                bb_touch = (c0_low <= bb_lower) if bb_lower > 0 else False
                pine_trigger = (pine_signal == 'Buy')
                
            if bb_touch or pine_trigger:
                c1_body = abs(c1_close - c1_open)
                buffer = c1_body * 0.03
                
                if is_long:
                    if c1_close > c1_open: # C1 verde
                        if c0_open >= c1_close:
                            sl_sipv = c1_close - buffer
                        else:
                            sl_sipv = c1_open
                    else: # C1 roja
                        if pine_trigger and current_gain > 0:
                            sl_sipv = current_price * 0.998 # 0.2% protection
                else: # is_short
                    if c1_close < c1_open: # C1 roja
                        if c0_open <= c1_close:
                            sl_sipv = c1_close + buffer
                        else:
                            sl_sipv = c1_open
                    else: # C1 verde
                        if pine_trigger and current_gain > 0:
                            sl_sipv = current_price * 1.002
                            
                if sl_sipv is not None:
                    if is_long and sl_sipv > state.current_sl:
                        return {
                            'action': 'update_sl',
                            'new_sl': round(sl_sipv, 8),
                            'new_level': 99,
                            'reason': f'Trailing SIPV Crypto: pine={pine_trigger}, bb={bb_touch} → SL a {sl_sipv:.6f}',
                        }
                    elif not is_long and sl_sipv < state.current_sl:
                        return {
                            'action': 'update_sl',
                            'new_sl': round(sl_sipv, 8),
                            'new_level': 99,
                            'reason': f'Trailing SIPV Crypto: pine={pine_trigger}, bb={bb_touch} → SL a {sl_sipv:.6f}',
                        }

        for i, (trigger, new_sl_pct) in enumerate(levels):
            level_idx = i + 1
            if current_gain >= trigger and state.trailing_level < level_idx:
                if is_long:
                    new_sl = entry * (1 + new_sl_pct)
                else:
                    new_sl = entry * (1 - new_sl_pct)

                if is_long:
                    if new_sl <= state.current_sl: continue
                else:
                    if new_sl >= state.current_sl: continue

                return {
                    'action':    'update_sl',
                    'new_sl':    round(new_sl, 8),
                    'new_level': level_idx,
                    'reason': (
                        f'Trailing nivel {level_idx}: '
                        f'+{trigger*100:.2f}% → SL a +{new_sl_pct*100:.2f}%'
                    ),
                }

    return {'action': 'none'}


def evaluate_break_even(
    state:         ProtectionState,
    current_price: float,
    df_15m:        pd.DataFrame = None,
) -> dict:
    """
    REGLA 1: Break-Even Automático.
    Mueve el SL al precio de entrada + buffer al alcanzar el umbral.
    """
    if state.be_activated:
        return {'action': 'none'}
        
    is_long = state.side.lower() in ('long', 'buy')
    
    # --- LÓGICA DE SUSPENSIÓN POR MOMENTUM EXPLOSIVO ---
    if df_15m is not None and len(df_15m) > 0:
        c0 = df_15m.iloc[-1]
        c0_high = float(c0.get('high', 0))
        c0_low = float(c0.get('low', 0))
        ema3 = float(c0.get('ema3', 0))
        ema9 = float(c0.get('ema9', 0))
        bb_upper = float(c0.get('upper_2', 0))
        bb_lower = float(c0.get('lower_2', 0))
        bb_expanding = bool(c0.get('bb_expanding', False))
        pine_signal = str(c0.get('pinescript_signal', ''))
        
        if is_long:
            momentum_fuerte = (ema3 > ema9) if (ema3 > 0 and ema9 > 0) else False
            condicion_explosiva = (c0_high >= bb_upper) or bb_expanding or (pine_signal == 'Sell') if bb_upper > 0 else False
            
            if momentum_fuerte and condicion_explosiva:
                return {'action': 'none'} # Suspendido por explosión alcista
        else:
            momentum_fuerte = (ema3 < ema9) if (ema3 > 0 and ema9 > 0) else False
            condicion_explosiva = (c0_low <= bb_lower) or bb_expanding or (pine_signal == 'Buy') if bb_lower > 0 else False
            
            if momentum_fuerte and condicion_explosiva:
                return {'action': 'none'} # Suspendido por explosión bajista
    # ---------------------------------------------------

    cfg  = PROTECTION_CONFIG.get(state.market_type, {})
    entry = state.entry_price
    side  = state.side.lower()

    pnl = calculate_pnl(entry, current_price, side, state.symbol, state.market_type)

    if state.market_type == 'forex_futures':
        trigger = cfg.get('be_trigger_pips', 8)
        buffer  = cfg.get('be_buffer_pips', 1)
        pip     = PIP_SIZES.get(state.symbol, 0.0001)

        if pnl['pips'] >= trigger:
            be_price = entry + (buffer * pip) if is_long else entry - (buffer * pip)
            return {
                'action':   'activate_be',
                'be_price': round(be_price, 6),
                'reason':   f'Break-Even: +{pnl["pips"]:.1f} pips ≥ {trigger} pips → SL a {be_price:.6f}'
            }
    else:  # crypto / stocks
        trigger = cfg.get('be_trigger_pct', 0.003)
        buffer  = cfg.get('be_buffer_pct', 0.0005)

        if pnl['pct'] / 100 >= trigger:
            be_price = entry * (1 + buffer) if is_long else entry * (1 - buffer)
            return {
                'action':   'activate_be',
                'be_price': round(be_price, 8),
                'reason':   f'Break-Even: +{pnl["pct"]:.3f}% ≥ {trigger*100:.2f}% → SL a {be_price:.8f}'
            }

    return {'action': 'none'}


def evaluate_inverse_signal(
    state:         ProtectionState,
    current_price: float,
    inverse_rule:  str,
) -> dict:
    """
    REGLA 2 + REGLA 5: Filtro inteligente para señales inversas.
    """
    cfg   = PROTECTION_CONFIG.get(state.market_type, {})
    pnl = calculate_pnl(state.entry_price, current_price, state.side, state.symbol, state.market_type)

    original_sl   = state.original_sl
    entry = state.entry_price
    original_risk = abs(entry - original_sl) / entry if entry > 0 else 0.01

    min_cycles    = cfg.get('min_time_before_inverse_close', 2)
    max_loss_ratio = cfg.get('max_loss_before_inverse_close', 0.5)

    if pnl['is_profit']:
        return {
            'action': 'close_market',
            'reason': f'Señal inversa {inverse_rule} con ganancia +{pnl["pct"]:.3f}% → Asegurar',
            'pnl': pnl, 'urgent': False,
        }

    loss_pct = abs(pnl['pct']) / 100
    loss_ratio = loss_pct / original_risk if original_risk > 0 else 1.0

    if state.cycles_open < min_cycles and loss_ratio < max_loss_ratio:
        state.inverse_signal_cycles += 1
        return {
            'action': 'wait_confirmation',
            'reason': f'Señal inversa {inverse_rule}: posición joven ({state.cycles_open} ciclos), esperando...',
            'pnl': pnl, 'cycles_waiting': state.inverse_signal_cycles,
        }

    if loss_ratio >= max_loss_ratio:
        return {
            'action': 'close_market',
            'reason': f'Señal inversa {inverse_rule}: pérdida alta {pnl["pct"]:.3f}% ({loss_ratio*100:.0f}% del SL) → Cerrar',
            'pnl': pnl, 'urgent': True,
        }

    if state.inverse_signal_cycles >= 2:
        return {
            'action': 'close_market',
            'reason': f'Señal inversa confirmada ({state.inverse_signal_cycles}x) → Cerrar pérdida controlada',
            'pnl': pnl, 'urgent': False,
        }

    return {'action': 'wait_confirmation', 'pnl': pnl}


def evaluate_partial_close(
    state:         ProtectionState,
    current_price: float,
) -> dict:
    """
    REGLA 6: Cierre Parcial en zonas de TP.
    """
    if state.partial_closed:
        return {'action': 'none'}

    cfg  = PROTECTION_CONFIG.get(state.market_type, {})
    pnl = calculate_pnl(state.entry_price, current_price, state.side, state.symbol, state.market_type)

    if state.market_type == 'forex_futures':
        tp1 = cfg.get('partial_close_tp1_pips', 20)
        ratio = cfg.get('partial_close_ratio', 0.50)
        if pnl['pips'] >= tp1:
            return {
                'action':    'partial_close',
                'close_pct': ratio, 'tp_level': 1, 'move_sl_to_be': True,
                'reason':    f'TP1 alcanzado: +{pnl["pips"]:.1f} pips ≥ {tp1} pips → Cerrar {ratio*100:.0f}% + SL a BE'
            }
    else:
        tp1_pct = cfg.get('partial_close_tp1_pct', 0.008)
        ratio   = cfg.get('partial_close_ratio', 0.50)
        if pnl['pct'] / 100 >= tp1_pct:
            return {
                'action':    'partial_close',
                'close_pct': ratio, 'tp_level': 1, 'move_sl_to_be': True,
                'reason':    f'TP1 alcanzado: +{pnl["pct"]:.3f}% ≥ {tp1_pct*100:.2f}% → Cerrar {ratio*100:.0f}% + SL a BE'
            }

    return {'action': 'none'}


def evaluate_counter_trend_sizing(
    signal_direction: str,
    snap:             dict,
    market_type:      str = 'crypto_futures'
) -> dict:
    """
    REGLA 3: Reducción de tamaño en señales contra-tendencia.
    """
    cfg = PROTECTION_CONFIG.get(market_type, {})
    size_reduction = cfg.get('counter_trend_size_pct', 0.50)
    flags = []

    sar_4h = int(snap.get('sar_trend_4h') if snap.get('sar_trend_4h') is not None else 0) if snap else 0
    if signal_direction.lower() in ('long', 'buy') and sar_4h < 0:
        flags.append('SAR 4H bajista vs LONG')
    elif signal_direction.lower() in ('short', 'sell') and sar_4h > 0:
        flags.append('SAR 4H alcista vs SHORT')

    mtf = float(snap.get('mtf_score') if snap.get('mtf_score') is not None else 0) if snap else 0
    if signal_direction.lower() in ('long', 'buy') and mtf < 0.20:
        flags.append(f'MTF débil para LONG ({mtf:.2f})')
    elif signal_direction.lower() in ('short', 'sell') and mtf > -0.20:
        flags.append(f'MTF débil para SHORT ({mtf:.2f})')

    adx = float(snap.get('adx') if snap.get('adx') is not None else 0) if snap else 0
    if adx > 35:
        plus_di  = float(snap.get('plus_di') if snap.get('plus_di') is not None else 0) if snap else 0
        minus_di = float(snap.get('minus_di') if snap.get('minus_di') is not None else 0) if snap else 0
        if signal_direction.lower() in ('long','buy') and minus_di > plus_di:
            flags.append(f'ADX fuerte bajista ({adx:.1f})')
        elif signal_direction.lower() not in ('long','buy') and plus_di > minus_di:
            flags.append(f'ADX fuerte alcista ({adx:.1f})')

    is_counter = len(flags) >= 2
    return {
        'is_counter_trend': is_counter,
        'flags': flags,
        'sizing_factor': size_reduction if is_counter else 1.0,
        'reason': f'Counter-trend: {len(flags)} flags → sizing {"50%" if is_counter else "100%"}'
    }


def check_cooldown(
    symbol:           str,
    last_close_cycle: int,
    current_cycle:    int,
    market_type:      str = 'crypto_futures'
) -> dict:
    """
    REGLA 7: Cooldown entre operaciones.
    """
    cfg      = PROTECTION_CONFIG.get(market_type, {})
    cooldown = cfg.get('cooldown_cycles', 2)
    cycles   = current_cycle - last_close_cycle
    in_cooldown = cycles < cooldown

    return {
        'in_cooldown': in_cooldown,
        'cycles_waited': cycles, 'cycles_needed': cooldown,
        'reason': f'{"⏳ Cooldown activo" if in_cooldown else "✅ Cooldown OK"}: {cycles}/{cooldown} ciclos'
    }


def evaluate_all_protections(
    state:         ProtectionState,
    current_price: float,
    snap:          Optional[dict] = None,
    inverse_rule:  Optional[str] = None,
    df_15m:        pd.DataFrame = None,
    df_5m:         pd.DataFrame = None,
) -> dict:
    """
    Función principal de evaluación por prioridades.
    """
    actions = []
    bb_touch_triggered = False

    # 1. Break-Even
    be = evaluate_break_even(state, current_price, df_15m=df_15m)
    if be['action'] == 'activate_be':
        actions.append({'priority': 1, 'type': 'break_even', **be})

    # 2. Trailing Stop
    trail = evaluate_trailing_stop(state, current_price, df_15m=df_15m, df_5m=df_5m, snap=snap)
    if trail.get('update_bb_touched') or trail['action'] == 'update_bb_touched':
        bb_touch_triggered = True

    if trail['action'] == 'update_sl':
        actions.append({'priority': 2, 'type': 'trailing', **trail})
    elif trail['action'] == 'close_market':
        actions.append({'priority': 2, 'type': 'trailing_close', **trail})

    # 3. Partial Close
    partial = evaluate_partial_close(state, current_price)
    if partial['action'] == 'partial_close':
        actions.append({'priority': 3, 'type': 'partial_close', **partial})

    # 4. Señal Inversa
    if inverse_rule:
        inv = evaluate_inverse_signal(state, current_price, inverse_rule)
        if inv['action'] in ('close_market', 'wait_confirmation'):
            actions.append({'priority': 4, 'type': 'inverse_signal', **inv})

    ret = {
        'has_action': False, 'primary': None, 'all_actions': [],
        'pnl': calculate_pnl(state.entry_price, current_price, state.side, state.symbol, state.market_type),
        'bb_touch_triggered': bb_touch_triggered,
        'bb_touched_val': getattr(state, 'bb_touched', False)
    }

    if actions:
        primary = min(actions, key=lambda x: x['priority'])
        ret.update({
            'has_action': True, 'primary': primary, 'all_actions': actions
        })

    return ret
