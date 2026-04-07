"""
eTrader v4.5 — Relative Volume (RVOL) Calculator
Central piece of the stocks volume analysis system.

RVOL = current_volume / average_volume_same_time_window

Unlike crypto where volume spikes are simple ratio-based,
stocks RVOL must account for:
  - Time-of-day patterns (opening/closing surges)
  - Pre-market vs regular session vs after-hours
  - Per-ticker historical baseline (same hour over 20 days)
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from app.core.logger import log_info, log_warning

MODULE = "rvol"


def calculate_rvol(
    df: pd.DataFrame,
    window: int = 20,
    time_adjusted: bool = True,
) -> pd.Series:
    """
    Calculate Relative Volume (RVOL) for each row in the DataFrame.

    Parameters
    ----------
    df             : DataFrame with 'volume' and 'open_time' columns
    window         : Rolling window for average (default 20 periods)
    time_adjusted  : If True, compare against same-hour average (stocks-specific)

    Returns
    -------
    pd.Series of RVOL values aligned to df index
    """
    if df is None or df.empty or "volume" not in df.columns:
        return pd.Series(dtype=float)

    volumes = df["volume"].astype(float)

    if time_adjusted and "open_time" in df.columns:
        return _time_adjusted_rvol(df, window)
    else:
        # Simple RVOL: current / rolling average
        avg_vol = volumes.rolling(window=window, min_periods=5).mean()
        rvol = volumes / avg_vol
        return rvol.fillna(1.0)


def _time_adjusted_rvol(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Time-adjusted RVOL: compare volume against same-time-of-day average.
    
    This prevents false positives at market open (9:30-10:00) and close (15:30-16:00)
    where volume is naturally higher.
    """
    df = df.copy()
    volumes = df["volume"].astype(float)

    # Extract hour from open_time
    if df["open_time"].dt.tz is None:
        times = df["open_time"]
    else:
        times = df["open_time"].dt.tz_convert("US/Eastern")

    df["_hour"] = times.dt.hour

    # Calculate average volume per hour
    rvol_series = pd.Series(index=df.index, dtype=float)

    for hour in df["_hour"].unique():
        mask = df["_hour"] == hour
        hour_volumes = volumes[mask]

        if len(hour_volumes) >= 5:
            avg = hour_volumes.rolling(window=min(window, len(hour_volumes)), min_periods=3).mean()
            rvol_series[mask] = hour_volumes / avg
        else:
            # Not enough data for this hour — use simple rolling
            avg = volumes.rolling(window=window, min_periods=5).mean()
            rvol_series[mask] = volumes[mask] / avg[mask]

    df.drop(columns=["_hour"], inplace=True, errors="ignore")
    return rvol_series.fillna(1.0)


def detect_volume_spike(
    rvol: float,
    threshold: float = 2.5,
) -> dict:
    """
    Detect if current RVOL constitutes a volume spike.

    Parameters
    ----------
    rvol      : Current RVOL value
    threshold : Multiplier threshold (default 2.5x)

    Returns
    -------
    dict: {detected: bool, rvol: float, strength: str}
    """
    if rvol is None or np.isnan(rvol):
        return {"detected": False, "rvol": 0.0, "strength": "none"}

    detected = rvol >= threshold

    if rvol >= 5.0:
        strength = "explosive"
    elif rvol >= 3.5:
        strength = "strong"
    elif rvol >= threshold:
        strength = "moderate"
    elif rvol >= 1.5:
        strength = "elevated"
    else:
        strength = "normal"

    return {
        "detected":  detected,
        "rvol":      round(float(rvol), 2),
        "strength":  strength,
    }


def get_rvol_for_ticker(
    df: pd.DataFrame,
    window: int = 20,
    threshold: float = 2.5,
) -> dict:
    """
    Calculate RVOL and detect spikes for a single ticker DataFrame.

    Returns
    -------
    dict: {
        current_rvol: float,
        spike: dict,
        rvol_series: pd.Series,
        avg_volume: float,
        current_volume: int
    }
    """
    if df is None or df.empty:
        return {
            "current_rvol": 1.0,
            "spike": {"detected": False, "rvol": 1.0, "strength": "normal"},
            "rvol_series": pd.Series(dtype=float),
            "avg_volume": 0,
            "current_volume": 0,
        }

    rvol_series = calculate_rvol(df, window=window)
    current_rvol = float(rvol_series.iloc[-1]) if len(rvol_series) > 0 else 1.0
    spike = detect_volume_spike(current_rvol, threshold)

    avg_vol = float(df["volume"].astype(float).tail(window).mean())
    current_vol = int(df["volume"].iloc[-1])

    return {
        "current_rvol":   round(current_rvol, 2),
        "spike":          spike,
        "rvol_series":    rvol_series,
        "avg_volume":     round(avg_vol, 0),
        "current_volume": current_vol,
    }
