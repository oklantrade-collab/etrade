import pandas as pd
import numpy as np

MODULE = "HALCON_CENTINELA"

def calculate_score_15m(df_15m: pd.DataFrame, direction: str, params: dict) -> dict:
    """Score 15m (-100 to +100):
    - EMA3/EMA9 cross analysis + HH/LL structure on last 3 CLOSED candles (exclude current):
      - LOWs ascending + EMA3>EMA9 cross confirmed or in progress → +50 (maintain LONG)
      - HIGHs descending + cross not achieved → -50 (close LONG)
    - EMA9/EMA20 cross adds ±30 (higher hierarchy trend)
    Score = sum of both, clamped [-100, 100]
    Returns: {'score': int, 'components': {'ema3_ema9': int, 'ema9_ema20': int}, 'detail': str}
    """
    if df_15m is None or df_15m.empty or len(df_15m) < 4:
        return {'score': 0, 'components': {'ema3_ema9': 0, 'ema9_ema20': 0}, 'detail': 'Not enough data'}

    df = df_15m.iloc[:-1]
    if len(df) < 3:
        return {'score': 0, 'components': {'ema3_ema9': 0, 'ema9_ema20': 0}, 'detail': 'Not enough closed candles'}

    required_cols = ['high', 'low', 'ema_3', 'ema_9', 'ema_20']
    if not all(c in df.columns for c in required_cols):
        return {'score': 0, 'components': {'ema3_ema9': 0, 'ema9_ema20': 0}, 'detail': 'Missing columns'}

    last_3 = df.iloc[-3:]
    
    lows = last_3['low'].values
    highs = last_3['high'].values
    
    lows_ascending = (lows[1] > lows[0]) and (lows[2] > lows[1])
    highs_descending = (highs[1] < highs[0]) and (highs[2] < highs[1])
    
    last_ema3 = last_3['ema_3'].iloc[-1]
    last_ema9 = last_3['ema_9'].iloc[-1]
    last_ema20 = last_3['ema_20'].iloc[-1]
    
    cross_3_9 = (last_ema3 > last_ema9)
    
    score_3_9 = 0
    if lows_ascending and cross_3_9:
        score_3_9 = 50
    elif highs_descending and not cross_3_9:
        score_3_9 = -50
        
    score_9_20 = 0
    if last_ema9 > last_ema20:
        score_9_20 = 30
    elif last_ema9 < last_ema20:
        score_9_20 = -30
        
    total = max(-100, min(100, int(score_3_9 + score_9_20)))
    
    return {
        'score': total,
        'components': {'ema3_ema9': score_3_9, 'ema9_ema20': score_9_20},
        'detail': 'Calculated 15m structure and crosses'
    }
