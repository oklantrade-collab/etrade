"""
eTrade v3 — Volume Exhaustion Detection + Reversal Candle Patterns
For confirming Take Profit, entry signals, and IA candlestick context.
"""
import pandas as pd
import numpy as np


def detect_volume_signals(
    df: pd.DataFrame, vol_ema_period: int = 20
) -> pd.DataFrame:
    """
    Detect volume-based signals for entry and exit confirmation.

    Signals:
      vol_decreasing → confirms LONG TP (bullish exhaustion)
      vol_increasing → confirms SHORT TP (selling pressure)
      vol_entry_ok   → confirms sufficient liquidity for entry (>= 70% vol_ema)

    Parameters
    ----------
    df : DataFrame with 'volume' column
    vol_ema_period : period for volume EMA (default 20)

    Returns
    -------
    DataFrame with vol_ema, vol_slope_3, vol_decreasing, vol_increasing, vol_entry_ok
    """
    df = df.copy()

    df["vol_ema"] = df["volume"].ewm(span=vol_ema_period, adjust=False).mean()
    df["vol_slope_3"] = (df["volume"] - df["volume"].shift(3)) / (
        df["volume"].shift(3) + 1e-10
    )

    df["vol_decreasing"] = (
        (df["volume"] < df["vol_ema"])
        & (df["volume"] < df["volume"].shift(1))
        & (df["vol_slope_3"] < 0)
    )
    df["vol_increasing"] = (
        (df["volume"] > df["vol_ema"])
        & (df["volume"] > df["volume"].shift(1))
        & (df["vol_slope_3"] > 0)
    )
    # Minimum 70% of average to confirm entry with liquidity
    df["vol_entry_ok"] = df["volume"] >= df["vol_ema"] * 0.7

    return df


def detect_reversal_candles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect reversal candle patterns for position close confirmation and IA signals.

    Patterns detected:
    - is_gravestone: Gravestone Doji (upper shadow > 2x body, bearish reversal)
    - is_dragonfly: Dragonfly Doji (lower shadow > 2x body, bullish reversal)
    - is_doji: Generic Doji (body < 10% of total range)
    - is_red_candle / is_green_candle: Basic color
    - high_lower_than_prev: Higher high failure (bullish exhaustion)
    - low_higher_than_prev: Lower low failure (bearish exhaustion)

    Parameters
    ----------
    df : DataFrame with open, high, low, close columns

    Returns
    -------
    DataFrame with all pattern detection columns
    """
    df = df.copy()

    body = abs(df["close"] - df["open"])
    upper = df["high"] - df[["close", "open"]].max(axis=1)
    lower = df[["close", "open"]].min(axis=1) - df["low"]
    total = df["high"] - df["low"]

    # Gravestone Doji: long upper shadow, no lower shadow
    df["is_gravestone"] = (
        (upper > 2 * body) & (lower < body * 0.3) & (total > 0)
    )

    # Dragonfly Doji: long lower shadow, no upper shadow
    df["is_dragonfly"] = (
        (lower > 2 * body) & (upper < body * 0.3) & (total > 0)
    )

    # Generic Doji: tiny body relative to range
    df["is_doji"] = body < (total * 0.10)

    # Basic candle color
    df["is_red_candle"] = df["close"] < df["open"]
    df["is_green_candle"] = df["close"] > df["open"]

    # Exhaustion patterns
    df["high_lower_than_prev"] = df["high"] < df["high"].shift(1)
    df["low_higher_than_prev"] = df["low"] > df["low"].shift(1)

    # Engulfing patterns
    df["is_bullish_engulfing"] = (
        (df["close"] > df["open"])
        & (df["open"].shift(1) > df["close"].shift(1))
        & (df["close"] > df["open"].shift(1))
        & (df["open"] < df["close"].shift(1))
    )
    df["is_bearish_engulfing"] = (
        (df["close"] < df["open"])
        & (df["close"].shift(1) > df["open"].shift(1))
        & (df["open"] > df["close"].shift(1))
        & (df["close"] < df["open"].shift(1))
    )

    return df


def check_price_touched_zone(
    df: pd.DataFrame,
    zone_col: str,
    lookback: int = 3,
) -> pd.Series:
    """
    Check if the price touched a specific Fibonacci zone in the last N candles.

    Parameters
    ----------
    df : DataFrame with 'low', 'high' and the zone column
    zone_col : column name for the zone level (e.g., 'lower_5')
    lookback : number of candles to check (default 3)

    Returns
    -------
    Boolean Series — True if price touched the zone within lookback
    """
    result = pd.Series(False, index=df.index)
    if zone_col not in df.columns:
        return result

    for i in range(lookback):
        result = result | (df["low"].shift(i) <= df[zone_col].shift(i))

    return result
