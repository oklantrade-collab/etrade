import pandas as pd
import numpy as np

MODULE = "HALCON_CENTINELA"

def calculate_rsi_adjustment(df: pd.DataFrame, timeframe: str, regime: str,
                              entry_profile: str, params: dict) -> int:
    """RSI transversal component (added to each timeframe's score):
    - RSI < 20 (oversold) → +25 (favorable to close SHORT / maintain LONG)
    - RSI > 80 (overbought) → -25 (favorable to close LONG / maintain SHORT)
    - In strong trend regime (adx>30) AND entry_profile != ALTA_VOLATILIDAD:
      extreme level points reduced by 50% (RSI can stay extreme in trends)
    - Divergence: price makes new high/low but RSI doesn't confirm
      over last 3 CLOSED candles → ±35 (more weight than extreme, never reduced)
    Returns: int adjustment points (already signed)
    """
    if df is None or df.empty or len(df) < 4:
        return 0
        
    df_closed = df.iloc[:-1]
    if len(df_closed) < 3 or 'rsi' not in df_closed.columns:
        return 0
        
    last_row = df_closed.iloc[-1]
    rsi_val = last_row.get('rsi', np.nan)
    
    score_extreme = 0
    if pd.notna(rsi_val):
        if rsi_val < 20:
            score_extreme = 25
        elif rsi_val > 80:
            score_extreme = -25
            
    if regime == 'strong_trend' and entry_profile != 'ALTA_VOLATILIDAD':
        score_extreme *= 0.5
        
    # Divergence calculation over last 3 CLOSED candles
    last_3 = df_closed.iloc[-3:]
    price_highs = last_3['high'].values
    price_lows = last_3['low'].values
    rsi_vals = last_3['rsi'].values
    
    score_divergence = 0
    if len(price_highs) == 3:
        # Bearish divergence: price higher high, RSI lower high
        if price_highs[2] > price_highs[0] and rsi_vals[2] < rsi_vals[0]:
            score_divergence = -35
        # Bullish divergence: price lower low, RSI higher low
        elif price_lows[2] < price_lows[0] and rsi_vals[2] > rsi_vals[0]:
            score_divergence = 35
            
    total_adj = int(score_extreme + score_divergence)
    return max(-100, min(100, total_adj))
