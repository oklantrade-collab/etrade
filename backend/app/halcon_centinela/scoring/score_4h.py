import pandas as pd
import numpy as np

MODULE = "HALCON_CENTINELA"

def calculate_score_4h(df_4h: pd.DataFrame, direction: str, params: dict) -> dict:
    """Score 4H (-100 to +100):
    - EMA3 slope over last 3 CLOSED candles:
      - All 3 ascending (each ema_3 > previous) → +60
      - All 3 descending → -60
      - Mixed → proportional 0 to ±20
    Returns: {'score': int, 'components': {'ema3_slope': int}, 'detail': str}
    """
    if df_4h is None or df_4h.empty or len(df_4h) < 4:
        return {'score': 0, 'components': {'ema3_slope': 0}, 'detail': 'Not enough data'}

    df = df_4h.iloc[:-1]  # closed only
    if len(df) < 4 or 'ema_3' not in df.columns:
        return {'score': 0, 'components': {'ema3_slope': 0}, 'detail': 'Missing ema_3 or data'}

    last_4 = df.iloc[-4:]['ema_3'].values
    
    diffs = np.diff(last_4)  # 3 differences
    
    score_slope = 0
    if all(d > 0 for d in diffs):
        score_slope = 60
    elif all(d < 0 for d in diffs):
        score_slope = -60
    else:
        # Mixed
        pos_count = sum(1 for d in diffs if d > 0)
        if pos_count > 1:
            score_slope = 20
        elif pos_count < 2:
            score_slope = -20
            
    score_slope = max(-100, min(100, int(score_slope)))
    
    return {
        'score': score_slope,
        'components': {'ema3_slope': score_slope},
        'detail': 'Calculated 4H EMA3 slope score'
    }
