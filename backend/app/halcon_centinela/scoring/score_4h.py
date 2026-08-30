import pandas as pd
import numpy as np

MODULE = "HALCON_CENTINELA"

def calculate_score_4h(df_4h: pd.DataFrame, direction: str, params: dict) -> dict:
    """Score 4H (-100 to +100):
    - EMA3 vs EMA9 on 4H:
      - ema_3 > ema_9 → +50 for LONG / -50 for SHORT
      - ema_3 < ema_9 → -50 for LONG / +50 for SHORT
    - EMA3 slope over last 3 CLOSED candles (±40)
    Returns: {'score': int, 'components': {'ema_cross': int, 'ema3_slope': int}, 'detail': str}
    """
    if df_4h is None or df_4h.empty or len(df_4h) < 4:
        return {'score': 0, 'components': {'ema_cross': 0, 'ema3_slope': 0}, 'detail': 'Not enough data'}

    df = df_4h.iloc[:-1].copy()  # closed only
    if len(df) < 4:
        return {'score': 0, 'components': {'ema_cross': 0, 'ema3_slope': 0}, 'detail': 'Missing data'}

    if 'ema_3' not in df.columns and 'close' in df.columns:
        df['ema_3'] = df['close'].ewm(span=3, adjust=False).mean()
    if 'ema_9' not in df.columns and 'close' in df.columns:
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()

    # 1. Slope of EMA3 (Primary component: ±60)
    score_slope = 0
    if 'ema_3' in df.columns and len(df) >= 4:
        last_4 = df.iloc[-4:]['ema_3'].values
        diffs = np.diff(last_4)  # 3 differences
        if all(d > 0 for d in diffs):
            score_slope = 60 if direction == 'long' else -60
        elif all(d < 0 for d in diffs):
            score_slope = -60 if direction == 'long' else 60
        else:
            pos_count = sum(1 for d in diffs if d > 0)
            if pos_count > 1:
                score_slope = 20 if direction == 'long' else -20
            elif pos_count < 2:
                score_slope = -20 if direction == 'long' else 20

    # 2. EMA3 vs EMA9 on 4H (if ema_9 column is provided or can be accurately derived from long history >= 15 candles)
    score_ema_cross = 0
    if 'ema_9' in df_4h.columns or ('close' in df.columns and len(df) >= 15):
        if 'ema_9' not in df.columns and 'close' in df.columns:
            df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        if 'ema_3' in df.columns and 'ema_9' in df.columns:
            ema3_val = float(df['ema_3'].iloc[-1])
            ema9_val = float(df['ema_9'].iloc[-1])
            if ema3_val > ema9_val:
                score_ema_cross = 30 if direction == 'long' else -30
            else:
                score_ema_cross = -30 if direction == 'long' else 30

    total_score = score_slope + score_ema_cross
    total_score = max(-100, min(100, int(total_score)))
    
    return {
        'score': total_score,
        'components': {'ema_cross': score_ema_cross, 'ema3_slope': score_slope},
        'detail': f"Calculated 4H score: slope={score_slope}, ema_cross={score_ema_cross}"
    }

