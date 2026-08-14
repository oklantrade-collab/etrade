import pandas as pd
import numpy as np

MODULE = "HALCON_CENTINELA"

def calculate_score_1d(df_1d: pd.DataFrame, direction: str, params: dict) -> dict:
    """Score 1D (-100 to +100):
    - Bollinger: price above upper band (upper_6) → +40 base (favorable SHORT close signal)
      price below lower band (lower_6) → -40 base (favorable LONG close signal)
    - EMA3 slope vs BASIS: if EMA3 has descending slope over last 3 CLOSED candles
      AND price near BASIS → -30 (unfavorable for LONG) / +30 (unfavorable for SHORT)
    - SIPV unfavorable candle pattern in formation → ±20
      SIPV detection: engulfing bearish, doji with long upper wick at resistance, etc.
      Check using candle body vs wick ratios on last 3 closed candles
    Score = sum, clamped to [-100, 100]
    Returns: {'score': int, 'components': {'bollinger': int, 'ema3_basis': int, 'sipv': int}, 'detail': str}
    """
    if df_1d is None or df_1d.empty or len(df_1d) < 5:
        return {'score': 0, 'components': {'bollinger': 0, 'ema3_basis': 0, 'sipv': 0}, 'detail': 'Not enough data'}

    df = df_1d.iloc[:-1]  # Exclude forming candle
    if len(df) < 4:
        return {'score': 0, 'components': {'bollinger': 0, 'ema3_basis': 0, 'sipv': 0}, 'detail': 'Not enough closed candles'}

    last_row = df.iloc[-1]
    
    score_bollinger = 0
    close_price = last_row.get('close', 0)
    
    # Bollinger component
    if 'upper_6' in df.columns and close_price > last_row['upper_6']:
        score_bollinger = 40  # favorable SHORT close signal, unfavorable LONG
    elif 'lower_6' in df.columns and close_price < last_row['lower_6']:
        score_bollinger = -40 # favorable LONG close signal, unfavorable SHORT

    # EMA3 slope vs BASIS
    score_ema3_basis = 0
    if 'ema_3' in df.columns and 'basis' in df.columns:
        last_3 = df.iloc[-3:]
        ema_3_vals = last_3['ema_3'].values
        # Descending slope
        if ema_3_vals[0] > ema_3_vals[1] > ema_3_vals[2]:
            basis_price = last_row['basis']
            atr = last_row.get('atr', basis_price * 0.01)
            if abs(close_price - basis_price) <= atr * 0.5: # near basis
                score_ema3_basis = -30 if direction == 'long' else 30

    # SIPV unfavorable candle pattern
    score_sipv = 0
    last_3 = df.iloc[-3:]
    for _, row in last_3.iterrows():
        c_open, c_close, c_high, c_low = row.get('open', 0), row.get('close', 0), row.get('high', 0), row.get('low', 0)
        body = abs(c_close - c_open)
        upper_wick = c_high - max(c_open, c_close)
        lower_wick = min(c_open, c_close) - c_low
        
        if direction == 'long':
            # Bearish signs: long upper wick, bearish body
            if upper_wick > body * 2 and c_close < c_open:
                score_sipv -= 10
        else:
            # Bullish signs for short: long lower wick, bullish body
            if lower_wick > body * 2 and c_close > c_open:
                score_sipv += 10
                
    score_sipv = max(-20, min(20, score_sipv))

    total_score = score_bollinger + score_ema3_basis + score_sipv
    total_score = max(-100, min(100, int(total_score)))

    return {
        'score': total_score,
        'components': {
            'bollinger': score_bollinger,
            'ema3_basis': score_ema3_basis,
            'sipv': score_sipv
        },
        'detail': 'Calculated 1D score'
    }
