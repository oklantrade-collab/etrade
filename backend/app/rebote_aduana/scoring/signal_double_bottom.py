import pandas as pd
import numpy as np

MODULE = "REBOTE_ADUANA"

def _safe_float(val, default=0.0):
    try:
        return float(val) if not pd.isna(val) else default
    except (ValueError, TypeError):
        return default

def calculate_signal_double_bottom(df_5m: pd.DataFrame, df_15m: pd.DataFrame, direction: str, params: dict) -> dict:
    """
    Signal S2: Double bottom/top on 5m + confirmation from 2 closed 15m candles (weight 35).
    """
    result = {'score': 0, 'triggered': False, 'components': {}, 'detail': ''}
    
    if df_5m is None or df_5m.empty or len(df_5m) < 22:
        result['detail'] = 'Not enough 5m data'
        return result
        
    if df_15m is None or df_15m.empty or len(df_15m) < 3:
        result['detail'] = 'Not enough 15m data'
        return result
        
    required_cols_5m = ['low', 'high', 'atr']
    if not all(c in df_5m.columns for c in required_cols_5m):
        result['detail'] = 'Missing OHLC or ATR columns in 5m'
        return result
        
    required_cols_15m = ['close']
    if not all(c in df_15m.columns for c in required_cols_15m):
        result['detail'] = 'Missing close column in 15m'
        return result

    # Use closed candles
    closed_5m = df_5m.iloc[:-1]
    closed_15m = df_15m.iloc[:-1]
    
    # Get last 2 closed 15m candles
    last_15m_close = _safe_float(closed_15m['close'].iloc[-1])
    prev_15m_close = _safe_float(closed_15m['close'].iloc[-2])
    
    # Check 15m confirmation
    dir_upper = str(direction).upper()
    confirmed_15m = False
    if dir_upper == 'LONG':
        confirmed_15m = last_15m_close > prev_15m_close
    elif dir_upper == 'SHORT':
        confirmed_15m = last_15m_close < prev_15m_close
        
    if not confirmed_15m:
        result['detail'] = f"15m confirmation failed for {direction}"
        return result
        
    # Check 5m pattern (lookback 20)
    lookback_df = closed_5m.iloc[-20:]
    current_atr = _safe_float(closed_5m['atr'].iloc[-1], 1.0)
    tolerance = current_atr * 0.3
    
    pattern_found = False
    p1 = 0.0
    p2 = 0.0
    
    if dir_upper == 'LONG':
        # Find double bottom
        lows = lookback_df['low'].values
        # Simple scan: find absolute minimum in first half, and another near minimum in second half
        mid = len(lows) // 2
        first_half = lows[:mid]
        second_half = lows[mid:]
        if len(first_half) > 0 and len(second_half) > 0:
            b1 = np.min(first_half)
            b2 = np.min(second_half)
            if abs(b1 - b2) <= tolerance and b2 >= b1:
                pattern_found = True
                p1, p2 = b1, b2
                
    elif dir_upper == 'SHORT':
        # Find double top
        highs = lookback_df['high'].values
        mid = len(highs) // 2
        first_half = highs[:mid]
        second_half = highs[mid:]
        if len(first_half) > 0 and len(second_half) > 0:
            t1 = np.max(first_half)
            t2 = np.max(second_half)
            if abs(t1 - t2) <= tolerance and t2 <= t1:
                pattern_found = True
                p1, p2 = t1, t2

    if pattern_found:
        score = params.get('w_double_bottom_top', 35)
        result['score'] = score
        result['triggered'] = True
        result['components'] = {
            'pattern': 'double_bottom' if direction == 'LONG' else 'double_top',
            'bottom1': p1,
            'bottom2': p2,
            'confirmed_15m': confirmed_15m
        }
        result['detail'] = f"{result['components']['pattern']} detected and 15m confirmed"
    else:
        result['detail'] = f"No double top/bottom found for {direction}"
        
    return result
