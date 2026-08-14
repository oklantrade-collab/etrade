import pandas as pd

MODULE = "HALCON_CENTINELA"

def calculate_compression_index(df: pd.DataFrame, atr_daily: float, params: dict) -> dict:
    """EMA Compression Index:
    D1 = |EMA20 - EMA9| of last closed candle
    D2 = |EMA3 - EMA9| of last closed candle
    index = D2 / (D1 + 1e-10)  normalized by ATR
    IC < compression_threshold (0.15) → EMAs compressed → high reversal probability
    Returns: {'index': float, 'compressed': bool, 'reversal_probability': str}
    """
    if df is None or df.empty or len(df) < 2:
        return {'index': 0.0, 'compressed': False, 'reversal_probability': 'low'}
        
    df_closed = df.iloc[:-1]
    if df_closed.empty:
        return {'index': 0.0, 'compressed': False, 'reversal_probability': 'low'}
        
    last_closed = df_closed.iloc[-1]
    
    ema3 = last_closed.get('ema_3', 0)
    ema9 = last_closed.get('ema_9', 0)
    ema20 = last_closed.get('ema_20', 0)
    
    d1 = abs(ema20 - ema9)
    d2 = abs(ema3 - ema9)
    
    idx = d2 / (d1 + 1e-10)
    
    threshold = params.get('compression_threshold', 0.15)
    compressed = bool(idx < threshold)
    rev_prob = 'high' if compressed else 'low'
    
    return {
        'index': float(idx),
        'compressed': compressed,
        'reversal_probability': rev_prob
    }

def apply_fibonacci_multiplier(compression_result: dict, fib_zone: int) -> float:
    """Multiply reversal score based on Fibonacci zone when EMAs are compressed:
    BASIS (zone 0) → x1.0
    zone ±1 → x1.2
    zone ±2 → x1.4
    zone ±3 or beyond → x1.6
    Returns: multiplier float
    """
    if not compression_result.get('compressed', False):
        return 1.0
        
    abs_zone = abs(fib_zone)
    if abs_zone == 0:
        return 1.0
    elif abs_zone == 1:
        return 1.2
    elif abs_zone == 2:
        return 1.4
    else:
        return 1.6

def select_compression_timeframe(atr_pct_daily: float, params: dict) -> str:
    """Select timeframe for compression calculation:
    ATR% > 0.8% → '4h' (high volatility instruments)
    ATR% <= 0.8% → '15m' (normal volatility)
    Returns: timeframe string
    """
    threshold = params.get('volatility_threshold_pct', 0.8)
    if atr_pct_daily > threshold:
        return '4h'
    return '15m'
