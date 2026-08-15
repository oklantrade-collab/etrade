import pandas as pd
import numpy as np

MODULE = "REBOTE_ADUANA"

def _safe_float(val, default=0.0):
    try:
        return float(val) if not pd.isna(val) else default
    except (ValueError, TypeError):
        return default

def calculate_signal_fib_extreme(df_15m: pd.DataFrame, direction: str, params: dict) -> dict:
    """
    Signal S1: Touch of LOWER_6/UPPER_6 on 15m (weight 40).
    """
    result = {'score': 0, 'triggered': False, 'components': {}, 'detail': ''}
    
    if df_15m is None or df_15m.empty or len(df_15m) < 2:
        result['detail'] = 'Not enough 15m data'
        return result
        
    if 'fibonacci_zone' not in df_15m.columns:
        result['detail'] = 'Missing fibonacci_zone column'
        return result
        
    # Use last CLOSED candle
    closed_df = df_15m.iloc[:-1]
    last_idx = closed_df.index[-1]
    fib_zone = _safe_float(closed_df.at[last_idx, 'fibonacci_zone'], 0.0)
    
    max_score = params.get('w_fib_extreme_6', 40)
    
    score = 0
    dir_upper = str(direction).upper()
    if dir_upper == 'LONG':
        if fib_zone <= -6:
            score = max_score
        elif fib_zone == -5:
            score = 30
        elif fib_zone == -4:
            score = 20
    elif dir_upper == 'SHORT':
        if fib_zone >= 6:
            score = max_score
        elif fib_zone == 5:
            score = 30
        elif fib_zone == 4:
            score = 20
            
    if score > 0:
        result['score'] = score
        result['triggered'] = True
        result['components'] = {'fib_zone': fib_zone, 'fib_zone_value': f"Zone {fib_zone}"}
        result['detail'] = f"Fib zone {fib_zone} touch for {direction}"
    else:
        result['detail'] = f"No extreme fib zone touch for {direction}. Current zone: {fib_zone}"
        
    return result
