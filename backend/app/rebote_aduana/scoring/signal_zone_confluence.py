import pandas as pd
import numpy as np

MODULE = "REBOTE_ADUANA"

def _safe_float(val, default=0.0):
    try:
        return float(val) if not pd.isna(val) else default
    except (ValueError, TypeError):
        return default

def calculate_signal_zone_confluence(df_5m: pd.DataFrame, df_15m: pd.DataFrame, direction: str, params: dict) -> dict:
    """
    Signal S5: Zone LOWER_3-5/UPPER_3-5 + technical confluence (weight 15).
    """
    result = {'score': 0, 'triggered': False, 'components': {}, 'detail': ''}
    
    if df_5m is None or df_5m.empty or len(df_5m) < 2:
        result['detail'] = 'Not enough 5m data'
        return result
        
    if df_15m is None or df_15m.empty or len(df_15m) < 3:
        result['detail'] = 'Not enough 15m data'
        return result
        
    if 'fibonacci_zone' not in df_15m.columns:
        result['detail'] = 'Missing fibonacci_zone in 15m'
        return result
        
    if 'ema_3' not in df_5m.columns or 'ema_9' not in df_5m.columns:
        result['detail'] = 'Missing EMA columns in 5m'
        return result
        
    closed_15m = df_15m.iloc[:-1]
    closed_5m = df_5m.iloc[:-1]
    
    last_15m_fib = _safe_float(closed_15m['fibonacci_zone'].iloc[-1])
    
    # Check zone
    dir_upper = str(direction).upper()
    in_zone = False
    if dir_upper == 'LONG':
        in_zone = last_15m_fib in [-3, -4, -5]
    elif dir_upper == 'SHORT':
        in_zone = last_15m_fib in [3, 4, 5]
        
    if not in_zone:
        result['detail'] = f"Price not in zone 3-5 for {direction}. Current zone: {last_15m_fib}"
        return result
        
    # Check confluences
    confluences = []
    
    last_5m_ema3 = _safe_float(closed_5m['ema_3'].iloc[-1])
    last_5m_ema9 = _safe_float(closed_5m['ema_9'].iloc[-1])
    
    if dir_upper == 'LONG':
        if last_5m_ema3 > last_5m_ema9:
            confluences.append('ema_cross_5m')
            
        if 'macd_histogram' in df_5m.columns:
            if _safe_float(closed_5m['macd_histogram'].iloc[-1]) > 0:
                confluences.append('macd_hist_5m')
                
        if 'sar_trend' in df_15m.columns:
            sar_val = closed_15m['sar_trend'].iloc[-1]
            if sar_val in ('ascending', 1):
                confluences.append('sar_asc_15m')
                
        if 'ema_3' in df_15m.columns:
            ema3_last = _safe_float(closed_15m['ema_3'].iloc[-1])
            ema3_prev = _safe_float(closed_15m['ema_3'].iloc[-2])
            if ema3_last > ema3_prev:
                confluences.append('ema3_slope_15m')
                
    elif dir_upper == 'SHORT':
        if last_5m_ema3 < last_5m_ema9:
            confluences.append('ema_cross_5m')
            
        if 'macd_histogram' in df_5m.columns:
            if _safe_float(closed_5m['macd_histogram'].iloc[-1]) < 0:
                confluences.append('macd_hist_5m')
                
        if 'sar_trend' in df_15m.columns:
            sar_val = closed_15m['sar_trend'].iloc[-1]
            if sar_val in ('descending', -1):
                confluences.append('sar_desc_15m')
                
        if 'ema_3' in df_15m.columns:
            ema3_last = _safe_float(closed_15m['ema_3'].iloc[-1])
            ema3_prev = _safe_float(closed_15m['ema_3'].iloc[-2])
            if ema3_last < ema3_prev:
                confluences.append('ema3_slope_15m')
                
    if len(confluences) > 0:
        result['score'] = params.get('w_zone_confluence', 15)
        result['triggered'] = True
        result['components'] = {
            'zone': f"Zone {last_15m_fib}",
            'confluences': confluences
        }
        result['detail'] = f"Zone confluence triggered with: {', '.join(confluences)}"
    else:
        result['detail'] = "In zone but no technical confluence found"
        
    return result
