import pandas as pd
import numpy as np

MODULE = "HALCON_CENTINELA"

def calculate_score_5m(df_5m: pd.DataFrame, direction: str, params: dict) -> dict:
    """Score 5m (-100 to +100):
    Scenario A: EMA3>EMA9>EMA20, price above BASIS, 9+ candles without touching upper band,
                EMA3 starts descending → -40 for LONG (exhaustion without breakout)
    Scenario B: EMA3>EMA9>EMA20, price above upper band, squeeze active
                (bb_expanding or bb_width > bb_width_avg * 1.15) → +40 maintain LONG
    Returns: {'score': int, 'squeeze_active': bool, 'scenario': str, 'components': dict, 'detail': str}
    """
    default_res = {'score': 0, 'squeeze_active': False, 'scenario': 'None', 'components': {}, 'detail': 'Not enough data'}
    if df_5m is None or df_5m.empty or len(df_5m) < 10:
        return default_res
        
    df = df_5m.iloc[:-1]
    if len(df) < 10:
        return default_res

    upper_col = 'upper_6' if 'upper_6' in df.columns else 'upper_1'
    if upper_col not in df.columns or not all(c in df.columns for c in ['close', 'ema_3', 'ema_9', 'ema_20', 'basis']):
        return default_res
        
    last_row = df.iloc[-1]
    
    ema3 = last_row['ema_3']
    ema9 = last_row['ema_9']
    ema20 = last_row['ema_20']
    close_price = last_row['close']
    basis = last_row['basis']
    upper_band = last_row[upper_col]
    
    trend_up = (ema3 > ema9 > ema20)
    
    # Squeeze active check
    squeeze_active = False
    if 'bb_expanding' in df.columns and last_row.get('bb_expanding'):
        squeeze_active = True
    elif 'bb_width' in df.columns:
        bb_width_avg = df['bb_width'].rolling(20).mean().iloc[-1]
        if pd.notna(bb_width_avg) and last_row['bb_width'] > bb_width_avg * 1.15:
            squeeze_active = True

    score = 0
    scenario = 'None'
    
    if trend_up and close_price > basis:
        # Check if 9+ candles without touching upper band
        last_9 = df.iloc[-9:]
        touched_upper = (last_9['high'] >= last_9[upper_col]).any() if 'high' in last_9.columns else (last_9['close'] >= last_9[upper_col]).any()
        
        ema3_descending = df['ema_3'].iloc[-1] < df['ema_3'].iloc[-2]
        
        if not touched_upper and ema3_descending:
            score = -40
            scenario = 'A'
            
        elif close_price > upper_band and squeeze_active:
            score = 40
            scenario = 'B'
            
    score = max(-100, min(100, int(score)))
    
    return {
        'score': score,
        'squeeze_active': squeeze_active,
        'scenario': scenario,
        'components': {'scenario_score': score},
        'detail': f'Matched Scenario {scenario}'
    }
