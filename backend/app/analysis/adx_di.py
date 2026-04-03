"""
eTrade v3 — ADX + Directional Indicators
Full ADX calculation with +DI/-DI and crossover detection.
"""
import pandas as pd
import numpy as np


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Calculate ADX, +DI, -DI and detect directional crosses.

    ADX: trend strength (0-100, direction-agnostic)
    +DI: bullish movement strength
    -DI: bearish movement strength

    Also detects:
    - di_cross_bullish: +DI crosses above -DI
    - di_cross_bearish: -DI crosses above +DI
    - adx_rising: ADX trending upward over 3 bars

    Parameters
    ----------
    df : DataFrame with high, low, close columns
    period : ADX smoothing period (default 14)

    Returns
    -------
    DataFrame with adx, plus_di, minus_di, and crossover columns
    """
    df = df.copy()

    # True Range
    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1)),
        ),
    )

    # Directional Movement
    df["plus_dm"] = np.where(
        (df["high"] - df["high"].shift(1)) > (df["low"].shift(1) - df["low"]),
        np.maximum(df["high"] - df["high"].shift(1), 0),
        0,
    )
    df["minus_dm"] = np.where(
        (df["low"].shift(1) - df["low"]) > (df["high"] - df["high"].shift(1)),
        np.maximum(df["low"].shift(1) - df["low"], 0),
        0,
    )

    # Smoothed values using EMA
    atr_s = df["tr"].ewm(span=period, adjust=False).mean()
    plus_di_s = (
        100 * df["plus_dm"].ewm(span=period, adjust=False).mean() / atr_s
    )
    minus_di_s = (
        100 * df["minus_dm"].ewm(span=period, adjust=False).mean() / atr_s
    )

    # DX & ADX
    dx = 100 * abs(plus_di_s - minus_di_s) / (plus_di_s + minus_di_s + 1e-10)

    df["adx"] = dx.ewm(span=period, adjust=False).mean()
    df["plus_di"] = plus_di_s
    df["minus_di"] = minus_di_s

    # Crossovers
    df["di_cross_bullish"] = (df["plus_di"] > df["minus_di"]) & (
        df["plus_di"].shift(1) <= df["minus_di"].shift(1)
    )
    df["di_cross_bearish"] = (df["minus_di"] > df["plus_di"]) & (
        df["minus_di"].shift(1) <= df["plus_di"].shift(1)
    )

    # ADX rising (trend strengthening)
    df["adx_rising"] = df["adx"] > df["adx"].shift(3)

    # Clean up temp columns
    df.drop(columns=["tr", "plus_dm", "minus_dm"], inplace=True, errors="ignore")

    return df
