import pandas as pd
import numpy as np

MODULE = "REBOTE_ADUANA"

def _safe_float(val, default=0.0):
    try:
        return float(val) if not pd.isna(val) else default
    except (ValueError, TypeError):
        return default

def calculate_signal_rsi_extreme(df_15m: pd.DataFrame, df_5m: pd.DataFrame, direction: str, params: dict) -> dict:
    """
    Signal S4: RSI<15 (or >85) on 15m + ascending lows/descending highs on 5m (weight 25).
    """
    result = {'score': 0, 'triggered': False, 'components': {}, 'detail': ''}
    
    if df_15m is None or df_15m.empty or len(df_15m) < 2:
        result['detail'] = 'Not enough 15m data'
        return result
        
    if df_5m is None or df_5m.empty or len(df_5m) < 4:
        result['detail'] = 'Not enough 5m data'
        return result
        
    rsi_col = 'rsi' if 'rsi' in df_15m.columns else 'rsi_14'
    if rsi_col not in df_15m.columns:
        result['detail'] = 'Missing rsi column in 15m'
        return result
        
    required_cols_5m = ['low', 'high']
    if not all(c in df_5m.columns for c in required_cols_5m):
        result['detail'] = 'Missing OHLC in 5m'
        return result
        
    closed_15m = df_15m.iloc[:-1]
    closed_5m = df_5m.iloc[:-1]
    
    last_15m_rsi = _safe_float(closed_15m[rsi_col].iloc[-1])
    
    rsi_extreme = False
    structure_confirmed = False
    
    dir_upper = str(direction).upper()
    if dir_upper == 'LONG':
        rsi_extreme = last_15m_rsi < 15
        
        last_3_lows = closed_5m['low'].iloc[-3:].values
        if len(last_3_lows) == 3:
            structure_confirmed = (last_3_lows[2] > last_3_lows[1]) and (last_3_lows[1] > last_3_lows[0])
            
    elif dir_upper == 'SHORT':
        rsi_extreme = last_15m_rsi > 85
        
        last_3_highs = closed_5m['high'].iloc[-3:].values
        if len(last_3_highs) == 3:
            structure_confirmed = (last_3_highs[2] < last_3_highs[1]) and (last_3_highs[1] < last_3_highs[0])
            
    if rsi_extreme and structure_confirmed:
        result['score'] = params.get('w_rsi_extreme_structure', 25)
        result['triggered'] = True
        result['components'] = {
            'rsi_value': last_15m_rsi,
            'rsi_extreme': rsi_extreme,
            'structure_confirmed': structure_confirmed
        }
        result['detail'] = f"RSI extreme ({last_15m_rsi:.2f}) and structure confirmed for {direction}"
    else:
        result['detail'] = f"RSI or structure conditions not met for {direction}"
        
    return result
