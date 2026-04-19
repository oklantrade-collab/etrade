"""
ANTIGRAVITY · Candle Builder v1.0
Construye velas de 4H y 1D a partir de datos OHLCV de polling (5min/2min).

Mercados:
  Crypto: 48 períodos × 5min = 4H, 288 × 5min = 1D
  Forex:  48 períodos × 5min = 4H, 288 × 5min = 1D  
  Stocks: 120 períodos × 2min = 4H, 195 × 2min = 1D (sesión regular 6.5h)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.candle_signals.candle_patterns import CandleOHLC


# ─── PERÍODOS DE CONSTRUCCIÓN POR MERCADO ─────────────────────────────────────
CONSTRUCTION_PERIODS = {
    "4H": {
        "crypto": 48,    # 48  × 5min = 4h
        "forex":  48,    # 48  × 5min = 4h
        "stocks": 120,   # 120 × 2min = 4h
    },
    "1D": {
        "crypto": 288,   # 288 × 5min = 24h
        "forex":  288,   # 288 × 5min = 24h
        "stocks": 195,   # 195 × 2min = 6.5h (sesión regular NYSE/NASDAQ)
    },
}

# Polling intervals por mercado (minutos)
POLLING_INTERVALS = {
    "crypto": 5,
    "forex":  5,
    "stocks": 2,
}


@dataclass
class BuiltCandle:
    """A candle constructed from sub-period OHLCV data."""
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: Optional[float]     # Only for Stocks
    closed: bool              # True if all periods are filled
    timeframe: str            # "4H" or "1D"
    pair: str
    market: str               # "crypto" | "forex" | "stocks"
    session: Optional[str]    # "regular" | "premarket" | "afterhours" (stocks only)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_candle_ohlc(self) -> CandleOHLC:
        """Convert to CandleOHLC for pattern detection."""
        return CandleOHLC(
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


def build_candle_from_ohlcv(
    ohlcv_rows: list[dict],
    timeframe: str,
    market: str,
    pair: str,
    session: str = "regular",
) -> Optional[BuiltCandle]:
    """
    Build a 4H or 1D candle from a list of sub-period OHLCV dicts.
    
    Each row must have: open, high, low, close, volume
    Optional: price (for VWAP calc)
    
    Args:
        ohlcv_rows: list of OHLCV dictionaries (newest last)
        timeframe: "4H" or "1D"
        market: "crypto", "forex", or "stocks"
        pair: symbol/pair string
        session: for stocks — "regular", "premarket", "afterhours"
    
    Returns:
        BuiltCandle or None if insufficient data
    """
    required_periods = CONSTRUCTION_PERIODS.get(timeframe, {}).get(market)
    if not required_periods or not ohlcv_rows:
        return None

    # Take the last N rows
    window = ohlcv_rows[-required_periods:] if len(ohlcv_rows) >= required_periods else ohlcv_rows

    if not window:
        return None

    o = float(window[0].get("open", 0))
    h = max(float(r.get("high", 0)) for r in window)
    l = min(float(r.get("low", float("inf"))) for r in window)
    c = float(window[-1].get("close", 0))
    v = sum(float(r.get("volume", 0)) for r in window)

    # VWAP calculation (only meaningful for stocks)
    vwap = None
    if market == "stocks":
        total_pv = sum(
            float(r.get("close", 0)) * float(r.get("volume", 0))
            for r in window
        )
        total_v = sum(float(r.get("volume", 0)) for r in window)
        vwap = total_pv / total_v if total_v > 0 else None

    is_closed = len(window) >= required_periods

    return BuiltCandle(
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
        vwap=vwap,
        closed=is_closed,
        timeframe=timeframe,
        pair=pair,
        market=market,
        session=session if market == "stocks" else None,
    )


def build_candle_from_dataframe(
    df,
    timeframe: str,
    market: str,
    pair: str,
) -> Optional[BuiltCandle]:
    """
    Build a candle from a pandas DataFrame with columns:
    open, high, low, close, volume.
    
    Takes the last N rows according to market/timeframe configuration.
    """
    required_periods = CONSTRUCTION_PERIODS.get(timeframe, {}).get(market)
    if required_periods is None or df is None or len(df) == 0:
        return None

    # Map possible column names
    col_map = {}
    for col_name in ["open", "Open", "o"]:
        if col_name in df.columns:
            col_map["open"] = col_name
            break
    for col_name in ["high", "High", "h"]:
        if col_name in df.columns:
            col_map["high"] = col_name
            break
    for col_name in ["low", "Low", "l"]:
        if col_name in df.columns:
            col_map["low"] = col_name
            break
    for col_name in ["close", "Close", "c"]:
        if col_name in df.columns:
            col_map["close"] = col_name
            break
    for col_name in ["volume", "Volume", "v"]:
        if col_name in df.columns:
            col_map["volume"] = col_name
            break

    if not all(k in col_map for k in ["open", "high", "low", "close"]):
        return None

    window = df.tail(required_periods)
    if len(window) == 0:
        return None

    o = float(window.iloc[0][col_map["open"]])
    h = float(window[col_map["high"]].max())
    l = float(window[col_map["low"]].min())
    c = float(window.iloc[-1][col_map["close"]])
    
    vol_col = col_map.get("volume")
    v = float(window[vol_col].sum()) if vol_col else 0.0

    is_closed = len(window) >= required_periods

    # VWAP for stocks
    vwap = None
    if market == "stocks" and vol_col:
        total_pv = (window[col_map["close"]].astype(float) * window[vol_col].astype(float)).sum()
        total_v = window[vol_col].astype(float).sum()
        vwap = float(total_pv / total_v) if total_v > 0 else None

    return BuiltCandle(
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
        vwap=vwap,
        closed=is_closed,
        timeframe=timeframe,
        pair=pair,
        market=market,
        session="regular" if market == "stocks" else None,
    )
