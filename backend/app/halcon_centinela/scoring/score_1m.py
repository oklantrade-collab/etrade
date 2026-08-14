import pandas as pd
import numpy as np

MODULE = "HALCON_CENTINELA"

def calculate_score_1m(df_1m: pd.DataFrame, score_5m_result: dict, direction: str, params: dict) -> dict:
    """Score 1m (-100 to +100). Only active when 5m is in Scenario B (squeeze).
    - If not squeeze: return score=0
    - HIGHs of last 3 CLOSED 1m candles: if current forming candle doesn't surpass
      or stays below the previous highs → exhaustion signal → ±40
    - Requires EMA3 close to EMA9 (within ema_proximity_threshold_atr_pct of ATR)
    Returns: {'score': int, 'components': dict, 'detail': str}
    """
    default_res = {'score': 0, 'components': {}, 'detail': 'Not active or not enough data'}
    
    if not score_5m_result.get('squeeze_active', False) or score_5m_result.get('scenario') != 'B':
        return {'score': 0, 'components': {}, 'detail': '5m not in Scenario B'}
        
    if df_1m is None or df_1m.empty or len(df_1m) < 4:
        return default_res
        
    closed_df = df_1m.iloc[:-1]
    forming_candle = df_1m.iloc[-1]
    
    if len(closed_df) < 3 or 'high' not in df_1m.columns or 'ema_3' not in df_1m.columns or 'ema_9' not in df_1m.columns:
        return default_res
        
    last_3_closed_highs = closed_df.iloc[-3:]['high'].values
    max_closed_high = max(last_3_closed_highs)
    
    forming_high = forming_candle.get('high', 0)
    
    atr = forming_candle.get('atr', 0.001)
    if not atr or pd.isna(atr) or atr == 0:
        atr = 0.001
        
    ema3 = forming_candle.get('ema_3', 0)
    ema9 = forming_candle.get('ema_9', 0)
    
    proximity_pct = params.get('ema_proximity_threshold_atr_pct', 0.5)
    
    score = 0
    if abs(ema3 - ema9) <= proximity_pct * atr:
        if forming_high <= max_closed_high:
            score = -40 if direction == 'long' else 40
            
    score = max(-100, min(100, int(score)))
    
    return {
        'score': score,
        'components': {'exhaustion': score},
        'detail': 'Calculated 1m squeeze exhaustion'
    }
