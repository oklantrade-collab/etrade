"""
Level Evaluator for CASCADA — Rebote vs Continuation Check.
eTrade v5.0 — Spec Section 3.3, 3.4 & 3.5
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional


def check_rebote(
    direction: str,
    radar_snapshot: Dict[str, Any],
    pnl_current: float,
    current_level: int
) -> Dict[str, Any]:
    """
    Evaluates Section 3.3 (a): Chequeo de Rebote.
    Is the fast component of the crossed pair turning back against the trend,
    WHILE PnL is still positive?
    
    Refined by Section 3.5 EMA20 Slope:
    If EMA20 holds its original trend slope, fast component reversal is treated as 
    noise/pullback within intact trend, NOT a valid rebote.
    
    Returns:
        {
            'is_rebote': bool,
            'reason': str,
            'detail': str
        }
    """
    is_short = direction.lower() in ('short', 'sell')
    slope_ema3 = radar_snapshot.get('pendiente_EMA3', 'sin_datos')
    slope_ema20 = radar_snapshot.get('pendiente_EMA20', 'sin_datos')
    slope_matrix = radar_snapshot.get('slope_matrix', {})

    pnl_positive = pnl_current > 0

    if not pnl_positive:
        return {
            'is_rebote': False,
            'reason': 'PNL_NOT_POSITIVE',
            'detail': f"PnL (${pnl_current:.2f}) is not positive; rebote exit not applicable"
        }

    # For SHORT position (seeking falling prices):
    if is_short:
        # Rebound is fast EMA3 turning ASCENDING
        ema3_turned_up = (slope_ema3 == 'ascending')
        ema20_holds_down = (slope_ema20 == 'descending')

        if ema3_turned_up:
            if ema20_holds_down:
                # Section 3.5: Pullback in intact bearish trend -> NOT real reversal
                return {
                    'is_rebote': False,
                    'reason': 'PULLBACK_IN_INTACT_TREND',
                    'detail': 'EMA3 ascending but EMA20 descending: Short-term pullback in intact bearish trend (not real rebound)'
                }
            else:
                # Real rebound: EMA3 ascending and EMA20 lateral/ascending
                return {
                    'is_rebote': True,
                    'reason': 'REAL_REVERSAL_CONFIRMED',
                    'detail': f"Valid rebote detected at N{current_level}: EMA3 ascending and EMA20 not descending (PnL: ${pnl_current:.2f})"
                }

    # For LONG position (seeking rising prices):
    else:
        # Rebound/reversal is fast EMA3 turning DESCENDING
        ema3_turned_down = (slope_ema3 == 'descending')
        ema20_holds_up = (slope_ema20 == 'ascending')

        if ema3_turned_down:
            if ema20_holds_up:
                # Pullback in intact bullish trend -> NOT real reversal
                return {
                    'is_rebote': False,
                    'reason': 'PULLBACK_IN_INTACT_TREND',
                    'detail': 'EMA3 descending but EMA20 ascending: Short-term pullback in intact bullish trend (not real rebound)'
                }
            else:
                # Real reversal
                return {
                    'is_rebote': True,
                    'reason': 'REAL_REVERSAL_CONFIRMED',
                    'detail': f"Valid rebote detected at N{current_level}: EMA3 descending and EMA20 not ascending (PnL: ${pnl_current:.2f})"
                }

    return {
        'is_rebote': False,
        'reason': 'TREND_ALIGNED',
        'detail': 'Fast EMA aligned with position direction'
    }


def check_continuacion(
    direction: str,
    current_level: int,
    df_15m: Optional[pd.DataFrame],
    df_higher_tf: Optional[pd.DataFrame],  # 1h dataframe (used for N2-N5)
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Evaluates Section 3.3 (b) & 3.4: Chequeo de Continuación (Señales de Apoyo).
    
    Support signals:
    (i) Upper Bollinger band (15m) flattening or descending for SHORT (lower band rising for LONG).
    (ii) Highs/Lows descending/ascending over last 3 closed candles (15m in N1, 1h in N2-N5).
    
    Returns:
        {
            'confirmed': bool,
            'bb_signal': bool,
            'structure_signal': bool,
            'detail': str
        }
    """
    is_short = direction.lower() in ('short', 'sell')
    lookback = params.get('hh_lookback_candles', 3)

    # 1. Bollinger Band Support Signal (i) on 15m
    bb_signal = False
    if df_15m is not None and len(df_15m) >= 4:
        try:
            # Check upper band for SHORT, lower band for LONG
            band_col = 'upper_6' if is_short else 'lower_6'
            if band_col not in df_15m.columns:
                band_col = 'upper_1' if is_short else 'lower_1'

            if band_col in df_15m.columns:
                curr_band = float(df_15m[band_col].iloc[-2])
                prev_band = float(df_15m[band_col].iloc[-4])  # 2 candles back
                
                if is_short:
                    # Upper band flattening or descending
                    bb_signal = curr_band <= prev_band * 1.0005
                else:
                    # Lower band flattening or ascending
                    bb_signal = curr_band >= prev_band * 0.9995
        except Exception:
            bb_signal = False

    # 2. Price Structure Support Signal (ii)
    # 15m for N1, higher TF (1h) for N2-N5
    struct_df = df_15m if current_level <= 1 else (df_higher_tf if df_higher_tf is not None else df_15m)
    struct_signal = False

    if struct_df is not None and len(struct_df) >= lookback + 2:
        try:
            closed_candles = struct_df.iloc[-lookback - 1 : -1]
            if is_short:
                # Consecutive descending HIGHs
                highs = closed_candles['high'].values
                struct_signal = all(highs[i] >= highs[i + 1] for i in range(len(highs) - 1))
            else:
                # Consecutive ascending LOWs
                lows = closed_candles['low'].values
                struct_signal = all(lows[i] <= lows[i + 1] for i in range(len(lows) - 1))
        except Exception:
            struct_signal = False

    # Continuation is confirmed if at least one strong support signal holds
    confirmed = bb_signal or struct_signal

    tf_label = "15m" if current_level <= 1 else "1h"
    return {
        'confirmed': confirmed,
        'bb_signal': bb_signal,
        'structure_signal': struct_signal,
        'detail': (
            f"Continuation confirmed (BB signal: {bb_signal}, {tf_label} structure: {struct_signal})"
            if confirmed else
            f"Continuation not confirmed (BB signal: {bb_signal}, {tf_label} structure: {struct_signal})"
        )
    }
