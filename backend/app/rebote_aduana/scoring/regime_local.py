import pandas as pd

MODULE = "REBOTE_ADUANA"

def _safe_float(val, default=0.0):
    try:
        return float(val) if not pd.isna(val) else default
    except (ValueError, TypeError):
        return default

def classify_regime_local(df_15m: pd.DataFrame) -> dict:
    """
    Classifies local trend regime from EMA20/50/200 on 15m.
    Returns: {'regime': 'bullish'|'bearish'|'neutral', 'detail': str}
    """
    result = {'regime': 'neutral', 'detail': ''}
    
    if df_15m is None or df_15m.empty or len(df_15m) < 2:
        result['detail'] = 'Not enough 15m data'
        return result
        
    required = ['ema_20', 'ema_50', 'ema_200']
    if not all(c in df_15m.columns for c in required):
        result['detail'] = 'Missing EMA columns'
        return result
        
    closed_15m = df_15m.iloc[:-1]
    last_row = closed_15m.iloc[-1]
    
    ema20 = _safe_float(last_row['ema_20'])
    ema50 = _safe_float(last_row['ema_50'])
    ema200 = _safe_float(last_row['ema_200'])
    
    if ema20 > ema50 > ema200:
        result['regime'] = 'bullish'
        result['detail'] = 'EMA20 > EMA50 > EMA200'
    elif ema20 < ema50 < ema200:
        result['regime'] = 'bearish'
        result['detail'] = 'EMA20 < EMA50 < EMA200'
    else:
        result['regime'] = 'neutral'
        result['detail'] = 'EMAs interleaved'
        
    return result

def check_contra_trend_confirmation(df_15m: pd.DataFrame, direction: str) -> dict:
    """
    Checks reinforced confirmation for counter-trend entries (section 2.3.1).
    ALL THREE conditions must be met simultaneously:
    1. Lower Bollinger band (15m) ascending (for LONG in bearish regime)
    2. EMA3 > EMA9 (15m)
    3. EMA20 (15m) slope turning positive (no longer negative)
    Mirror for SHORT in bullish regime.
    Returns: {'confirmed': bool, 'conditions': {'bb_ascending': bool, 'ema_cross': bool, 'ema20_turning': bool}, 'detail': str}
    """
    result = {'confirmed': False, 'conditions': {}, 'detail': ''}
    
    if df_15m is None or df_15m.empty or len(df_15m) < 5:
        result['detail'] = 'Not enough 15m data'
        return result
        
    required = ['ema_3', 'ema_9', 'ema_20']
    if not all(c in df_15m.columns for c in required):
        result['detail'] = 'Missing required EMA columns'
        return result
        
    closed_15m = df_15m.iloc[:-1]
    
    # Extract last needed values
    last_ema3 = _safe_float(closed_15m['ema_3'].iloc[-1])
    last_ema9 = _safe_float(closed_15m['ema_9'].iloc[-1])
    
    last_ema20 = _safe_float(closed_15m['ema_20'].iloc[-1])
    prev_ema20 = _safe_float(closed_15m['ema_20'].iloc[-3]) # ema20[-4] logic from spec (2 closed candles ago)
    
    bb_condition = False
    ema_cross = False
    ema20_turning = False
    
    dir_upper = str(direction).upper()
    if dir_upper == 'LONG':
        # 1. Lower Bollinger Band ascending
        if 'lower_1' in closed_15m.columns:
            last_3_lower = closed_15m['lower_1'].iloc[-3:].values
            if len(last_3_lower) == 3:
                bb_condition = (last_3_lower[2] >= last_3_lower[1]) and (last_3_lower[1] >= last_3_lower[0])
        else:
            bb_condition = True # fallback if no column
            
        # 2. EMA3 > EMA9
        ema_cross = last_ema3 > last_ema9
        
        # 3. EMA20 slope turning positive
        ema20_turning = last_ema20 >= prev_ema20
        
    elif dir_upper == 'SHORT':
        # 1. Upper Bollinger Band descending
        if 'upper_1' in closed_15m.columns:
            last_3_upper = closed_15m['upper_1'].iloc[-3:].values
            if len(last_3_upper) == 3:
                bb_condition = (last_3_upper[2] <= last_3_upper[1]) and (last_3_upper[1] <= last_3_upper[0])
        else:
            bb_condition = True # fallback
            
        # 2. EMA3 < EMA9
        ema_cross = last_ema3 < last_ema9
        
        # 3. EMA20 slope turning negative
        ema20_turning = last_ema20 <= prev_ema20
        
    confirmed = bb_condition and ema_cross and ema20_turning
    
    result['confirmed'] = confirmed
    result['conditions'] = {
        'bb_condition': bb_condition,
        'ema_cross': ema_cross,
        'ema20_turning': ema20_turning
    }
    
    if confirmed:
        result['detail'] = f"Counter-trend confirmation met for {direction}"
    else:
        result['detail'] = f"Counter-trend confirmation failed for {direction}"
        
    return result
