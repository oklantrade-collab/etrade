import pandas as pd
import numpy as np

MODULE = "REBOTE_ADUANA"

def _safe_float(val, default=0.0):
    try:
        return float(val) if not pd.isna(val) else default
    except (ValueError, TypeError):
        return default

def calculate_signal_ema_squeeze(df_5m: pd.DataFrame, df_15m: pd.DataFrame, direction: str, params: dict) -> dict:
    """
    Signal S3: EMA3>EMA9 on 5m after Bollinger squeeze + extreme BB zone (weight 25).
    """
    result = {'score': 0, 'triggered': False, 'components': {}, 'detail': ''}
    
    if df_5m is None or df_5m.empty or len(df_5m) < 22:
        result['detail'] = 'Not enough 5m data'
        return result
        
    if df_15m is None or df_15m.empty or len(df_15m) < 3:
        result['detail'] = 'Not enough 15m data'
        return result
        
    required_cols_5m = ['ema_3', 'ema_9', 'bb_width']
    if not all(c in df_5m.columns for c in required_cols_5m):
        result['detail'] = 'Missing required columns in 5m (ema_3, ema_9, bb_width)'
        return result
        
    required_cols_15m = ['close', 'fibonacci_zone', 'lower_3', 'upper_3', 'basis'] # assuming basis exists for BB direction approximation, or lower_1 etc
    if not all(c in df_15m.columns for c in required_cols_15m):
        result['detail'] = 'Missing required columns in 15m'
        return result

    # Use closed candles
    closed_5m = df_5m.iloc[:-1]
    closed_15m = df_15m.iloc[:-1]
    
    # 5m conditions
    last_5m_ema3 = _safe_float(closed_5m['ema_3'].iloc[-1])
    last_5m_ema9 = _safe_float(closed_5m['ema_9'].iloc[-1])
    last_5m_bbw = _safe_float(closed_5m['bb_width'].iloc[-1])
    
    bbw_avg_20 = closed_5m['bb_width'].rolling(window=20).mean().iloc[-1]
    
    is_squeeze = last_5m_bbw < bbw_avg_20 or last_5m_bbw < 0.02
    
    dir_upper = str(direction).upper()
    ema_cross = False
    if dir_upper == 'LONG':
        ema_cross = last_5m_ema3 > last_5m_ema9
    else:
        ema_cross = last_5m_ema3 < last_5m_ema9
        
    # 15m conditions
    last_15m_close = _safe_float(closed_15m['close'].iloc[-1])
    last_15m_fib = _safe_float(closed_15m['fibonacci_zone'].iloc[-1])
    last_15m_lower3 = _safe_float(closed_15m['lower_3'].iloc[-1])
    last_15m_upper3 = _safe_float(closed_15m['upper_3'].iloc[-1])
    
    # BB direction approximation
    # If lower_1 exists we use it, else approximate
    has_lower1 = 'lower_1' in closed_15m.columns
    has_upper1 = 'upper_1' in closed_15m.columns
    
    extreme_zone = False
    bb_favorable = False
    
    if dir_upper == 'LONG':
        extreme_zone = (last_15m_fib <= -3) or (last_15m_close <= last_15m_lower3)
        if has_lower1:
            bb_favorable = _safe_float(closed_15m['lower_1'].iloc[-1]) >= _safe_float(closed_15m['lower_1'].iloc[-2])
        else:
            bb_favorable = True # Default pass if no column
    else:
        extreme_zone = (last_15m_fib >= 3) or (last_15m_close >= last_15m_upper3)
        if has_upper1:
            bb_favorable = _safe_float(closed_15m['upper_1'].iloc[-1]) <= _safe_float(closed_15m['upper_1'].iloc[-2])
        else:
            bb_favorable = True

    triggered = ema_cross and is_squeeze and extreme_zone and bb_favorable
    
    if triggered:
        result['score'] = params.get('w_ema_squeeze_bb', 25)
        result['triggered'] = True
        result['components'] = {
            'ema_cross': ema_cross,
            'squeeze': is_squeeze,
            'extreme_zone': extreme_zone,
            'bb_direction': 'favorable' if bb_favorable else 'unfavorable'
        }
        result['detail'] = f"EMA squeeze and BB extreme triggered for {direction}"
    else:
        result['detail'] = "Conditions not met for EMA squeeze signal"
        
    return result
