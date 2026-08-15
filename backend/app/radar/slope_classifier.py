"""
Slope Classifier for EMA3, EMA9, EMA20 normalized by ATR(14).
eTrade v5.0 — Spec Section 3.5
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from app.radar.config import SLOPE_THRESHOLDS


def classify_slope(
    df: pd.DataFrame, 
    ema_col: str, 
    atr_col: str = 'atr', 
    lookback: int = 3
) -> Dict[str, Any]:
    """
    Computes normalized EMA slope:
        pendiente_normalizada = (EMA_actual - EMA_hace_N_velas) / ATR(14)
    using only closed candles (excluding forming candle at iloc[-1]).
    
    Returns:
        {
            'ema_col': str,
            'slope_raw': float,
            'slope_normalized': float,
            'classification': 'ascending' | 'lateral' | 'descending' | 'sin_datos',
            'detail': str
        }
    """
    if df is None or len(df) < lookback + 2:
        return {
            'ema_col': ema_col,
            'slope_raw': 0.0,
            'slope_normalized': 0.0,
            'classification': 'sin_datos',
            'detail': f"Insufficient data (need at least {lookback + 2} candles)"
        }

    # Ensure required columns exist with fallback aliases
    actual_col = ema_col
    if actual_col not in df.columns:
        aliases = [ema_col.replace('_', ''), ema_col.upper(), ema_col.lower(), ema_col.upper().replace('_', '')]
        found = False
        for a in aliases:
            if a in df.columns:
                actual_col = a
                found = True
                break
        if not found:
            return {
                'ema_col': ema_col,
                'slope_raw': 0.0,
                'slope_normalized': 0.0,
                'classification': 'sin_datos',
                'detail': f"Column '{ema_col}' not found in dataframe"
            }

    # Closed candles: iloc[-2] is the last closed, iloc[-2 - lookback] is N candles back
    try:
        current_ema = df[actual_col].iloc[-2]
        past_ema = df[actual_col].iloc[-2 - lookback]
        
        # Check for NaN
        if pd.isna(current_ema) or pd.isna(past_ema):
            return {
                'ema_col': ema_col,
                'slope_raw': 0.0,
                'slope_normalized': 0.0,
                'classification': 'sin_datos',
                'detail': "NaN detected in EMA values"
            }

        slope_raw = float(current_ema - past_ema)

        # Get ATR
        atr_val = 0.0
        if atr_col in df.columns and not pd.isna(df[atr_col].iloc[-2]):
            atr_val = float(df[atr_col].iloc[-2])
        
        # If ATR is 0 or missing, calculate a simple proxy from high-low or default to 1.0
        if atr_val <= 0.0:
            if 'high' in df.columns and 'low' in df.columns:
                recent_ranges = (df['high'] - df['low']).iloc[-14:-1]
                atr_val = float(recent_ranges.mean()) if len(recent_ranges) > 0 else 1.0
            else:
                atr_val = 1.0

        slope_normalized = slope_raw / (atr_val if atr_val > 0 else 1.0)

        # Classify based on thresholds
        if slope_normalized > SLOPE_THRESHOLDS['ascending']:
            classification = 'ascending'
        elif slope_normalized < SLOPE_THRESHOLDS['descending']:
            classification = 'descending'
        else:
            classification = 'lateral'

        return {
            'ema_col': ema_col,
            'slope_raw': round(slope_raw, 6),
            'slope_normalized': round(slope_normalized, 4),
            'classification': classification,
            'detail': f"{ema_col} slope={slope_normalized:.4f} ({classification}) over {lookback} bars"
        }

    except Exception as e:
        return {
            'ema_col': ema_col,
            'slope_raw': 0.0,
            'slope_normalized': 0.0,
            'classification': 'sin_datos',
            'detail': f"Error computing slope: {str(e)}"
        }


def get_slope_matrix_interpretation(slope_ema3: str, slope_ema20: str) -> Dict[str, Any]:
    """
    Evaluates the EMA3 (speed) x EMA20 (trend) combination table (Spec Section 3.5):
    
    | EMA3 | EMA20 | Interpretation |
    | Ascending | Ascending | Tendencia fuerte confirmada |
    | Ascending | Lateral / Descending | Tendencia débil o en transición — precaución |
    | Descending | Ascending | Ruido de corto plazo (pullback) dentro de tendencia intacta |
    | Descending | Descending / Lateral | Reversión real probable |
    """
    if slope_ema3 == 'sin_datos' or slope_ema20 == 'sin_datos':
        return {
            'status': 'sin_datos',
            'is_strong_trend': False,
            'is_pullback_noise': False,
            'is_real_reversal': False,
            'detail': 'Faltan datos de pendiente'
        }

    if slope_ema3 == 'ascending' and slope_ema20 == 'ascending':
        return {
            'status': 'strong_trend_bullish',
            'is_strong_trend': True,
            'is_pullback_noise': False,
            'is_real_reversal': True,
            'detail': 'Tendencia fuerte confirmada (Alcista)'
        }
    elif slope_ema3 == 'descending' and slope_ema20 == 'descending':
        return {
            'status': 'strong_trend_bearish',
            'is_strong_trend': True,
            'is_pullback_noise': False,
            'is_real_reversal': True,
            'detail': 'Tendencia fuerte confirmada / Reversión real bajista'
        }
    elif slope_ema3 == 'descending' and slope_ema20 == 'ascending':
        return {
            'status': 'pullback_in_bullish_trend',
            'is_strong_trend': False,
            'is_pullback_noise': True,
            'is_real_reversal': False,
            'detail': 'Ruido de corto plazo (pullback) dentro de tendencia alcista intacta'
        }
    elif slope_ema3 == 'ascending' and slope_ema20 == 'descending':
        return {
            'status': 'pullback_in_bearish_trend',
            'is_strong_trend': False,
            'is_pullback_noise': True,
            'is_real_reversal': False,
            'detail': 'Ruido de corto plazo (pullback) dentro de tendencia bajista intacta'
        }
    elif slope_ema3 == 'descending' and slope_ema20 == 'lateral':
        return {
            'status': 'real_reversal_bearish',
            'is_strong_trend': False,
            'is_pullback_noise': False,
            'is_real_reversal': True,
            'detail': 'Reversión real probable (Bajista)'
        }
    elif slope_ema3 == 'ascending' and slope_ema20 == 'lateral':
        return {
            'status': 'real_reversal_bullish',
            'is_strong_trend': False,
            'is_pullback_noise': False,
            'is_real_reversal': True,
            'detail': 'Reversión real probable (Alcista)'
        }
    else:
        return {
            'status': 'transition',
            'is_strong_trend': False,
            'is_pullback_noise': False,
            'is_real_reversal': False,
            'detail': 'Tendencia débil o en transición — precaución'
        }
