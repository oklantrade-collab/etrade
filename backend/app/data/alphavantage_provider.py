"""
eTrader v4.5 — Alpha Vantage Data Provider
Replaces yfinance for US stocks OHLCV + Fundamental data.

API: https://www.alphavantage.co/
Rate Limits (Free): 25 calls/day — too slow for production.
Rate Limits (Premium): 75 calls/min, 500+/day — usable.

Endpoints Used:
  - TIME_SERIES_INTRADAY: 15m, 60m candles (5m, 30m also supported)
  - TIME_SERIES_DAILY: Daily candles (up to 20 years)
  - OVERVIEW: Company fundamentals (P/E, MarketCap, Sector, etc.)
  - GLOBAL_QUOTE: Current price snapshot
"""
import asyncio
import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase

MODULE = "alphavantage_provider"

# ── Rate Limiter ──
_last_call_ts: float = 0.0
_MIN_INTERVAL_S = 0.8  # ~75 calls/min safety margin


def _rate_limit():
    """Enforce minimum interval between API calls."""
    global _last_call_ts
    now = time.time()
    elapsed = now - _last_call_ts
    if elapsed < _MIN_INTERVAL_S:
        time.sleep(_MIN_INTERVAL_S - elapsed)
    _last_call_ts = time.time()


# ── Fundamental Cache (in-memory, refreshed once per day) ──
_fundamental_cache: dict[str, dict] = {}
_fundamental_cache_date: str = ""


class AlphaVantageProvider:
    """
    Provides OHLCV data and fundamental info for US equities via Alpha Vantage.
    
    Drop-in replacement for YFinanceProvider with identical method signatures.
    """

    BASE_URL = "https://www.alphavantage.co/query"

    # Map eTrader intervals → Alpha Vantage intervals
    INTERVAL_MAP = {
        "1m":  "1min",
        "5m":  "5min",
        "15m": "15min",
        "30m": "30min",
        "1h":  "60min",
        "4h":  "60min",   # Resample from 60min
        "1d":  None,       # Use TIME_SERIES_DAILY
        "1wk": None,       # Use TIME_SERIES_WEEKLY
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ALPHAVANTAGE_API_KEY", "")
        if not self.api_key:
            log_warning(MODULE, "No Alpha Vantage API key configured")

    def _request(self, params: dict) -> dict | None:
        """Make a rate-limited request to Alpha Vantage."""
        _rate_limit()
        params["apikey"] = self.api_key
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # Check for API errors
            if "Error Message" in data:
                log_error(MODULE, f"API Error: {data['Error Message']}")
                return None
            if "Note" in data:
                log_warning(MODULE, f"API Rate Limit: {data['Note']}")
                return None
            if "Information" in data:
                log_warning(MODULE, f"API Info: {data['Information']}")
                return None

            return data
        except Exception as e:
            log_error(MODULE, f"Request failed: {e}")
            return None

    # ── OHLCV Data ──────────────────────────────────────

    async def get_ohlcv(
        self,
        ticker: str,
        interval: str = "15m",
        period: str | None = None,
        limit: int = 200,
    ) -> pd.DataFrame | None:
        """
        Download OHLCV data for a ticker.

        Parameters
        ----------
        ticker   : US stock ticker (e.g. 'AAPL', 'MSFT')
        interval : Candle interval ('5m', '15m', '1h', '1d', etc.)
        period   : Ignored (Alpha Vantage uses outputsize + month params)
        limit    : Max number of candles to return.

        Returns
        -------
        DataFrame with columns: open_time, open, high, low, close, volume
        """
        try:
            needs_resample = interval == "4h"
            needs_daily = interval in ("1d", "1wk")

            if needs_daily:
                return await self._get_daily(ticker, interval, limit)

            av_interval = self.INTERVAL_MAP.get(interval)
            if av_interval is None:
                log_warning(MODULE, f"Unsupported interval: {interval}")
                return None

            params = {
                "function": "TIME_SERIES_INTRADAY",
                "symbol": ticker,
                "interval": "60min" if needs_resample else av_interval,
                "outputsize": "full",
                "adjusted": "true",
                "extended_hours": "false",
            }

            data = self._request(params)
            if not data:
                return None

            # Find the time series key
            ts_key = None
            for key in data:
                if "Time Series" in key:
                    ts_key = key
                    break

            if not ts_key or not data[ts_key]:
                log_warning(MODULE, f"No time series data for {ticker} {interval}")
                return None

            # Parse into DataFrame
            records = []
            for dt_str, values in data[ts_key].items():
                records.append({
                    "open_time": pd.Timestamp(dt_str),
                    "open":   float(values["1. open"]),
                    "high":   float(values["2. high"]),
                    "low":    float(values["3. low"]),
                    "close":  float(values["4. close"]),
                    "volume": int(float(values["5. volume"])),
                })

            df = pd.DataFrame(records)
            df = df.sort_values("open_time").reset_index(drop=True)

            # Timezone awareness
            if df["open_time"].dt.tz is None:
                df["open_time"] = df["open_time"].dt.tz_localize("US/Eastern").dt.tz_convert("UTC")
            else:
                df["open_time"] = df["open_time"].dt.tz_convert("UTC")

            # Resample to 4h if needed
            if needs_resample:
                df = df.set_index("open_time")
                df = df.resample("4h").agg({
                    "open":   "first",
                    "high":   "max",
                    "low":    "min",
                    "close":  "last",
                    "volume": "sum",
                }).dropna().reset_index()

            # Trim to limit
            if len(df) > limit:
                df = df.tail(limit).reset_index(drop=True)

            log_info(MODULE, f"Fetched {len(df)} candles for {ticker} {interval}")
            return df

        except Exception as e:
            log_error(MODULE, f"Error fetching {ticker} {interval}: {e}")
            return None

    async def _get_daily(
        self, ticker: str, interval: str, limit: int
    ) -> pd.DataFrame | None:
        """Fetch daily or weekly OHLCV data."""
        try:
            function = "TIME_SERIES_WEEKLY" if interval == "1wk" else "TIME_SERIES_DAILY_ADJUSTED"
            params = {
                "function": function,
                "symbol": ticker,
                "outputsize": "full",
            }

            data = self._request(params)
            if not data:
                return None

            # Find time series key
            ts_key = None
            for key in data:
                if "Time Series" in key or "Weekly" in key:
                    ts_key = key
                    break

            if not ts_key or not data[ts_key]:
                return None

            records = []
            for dt_str, values in data[ts_key].items():
                records.append({
                    "open_time": pd.Timestamp(dt_str),
                    "open":   float(values["1. open"]),
                    "high":   float(values["2. high"]),
                    "low":    float(values["3. low"]),
                    "close":  float(values.get("5. adjusted close", values["4. close"])),
                    "volume": int(float(values.get("6. volume", values.get("5. volume", 0)))),
                })

            df = pd.DataFrame(records)
            df = df.sort_values("open_time").reset_index(drop=True)

            if df["open_time"].dt.tz is None:
                df["open_time"] = df["open_time"].dt.tz_localize("UTC")

            if len(df) > limit:
                df = df.tail(limit).reset_index(drop=True)

            log_info(MODULE, f"Fetched {len(df)} daily candles for {ticker}")
            return df

        except Exception as e:
            log_error(MODULE, f"Error fetching daily {ticker}: {e}")
            return None

    # ── Ticker Info (Fundamentals) ─────────────────────

    async def get_ticker_info(self, ticker: str) -> dict | None:
        """
        Get fundamental info for a ticker via OVERVIEW endpoint.
        Cached per day to avoid burning API calls.
        """
        global _fundamental_cache, _fundamental_cache_date
        from datetime import date

        today = date.today().isoformat()
        if _fundamental_cache_date != today:
            _fundamental_cache.clear()
            _fundamental_cache_date = today

        if ticker in _fundamental_cache:
            return _fundamental_cache[ticker]

        try:
            params = {
                "function": "OVERVIEW",
                "symbol": ticker,
            }
            data = self._request(params)
            if not data or "Symbol" not in data:
                return None

            # Also get current price via GLOBAL_QUOTE
            price_data = self._request({
                "function": "GLOBAL_QUOTE",
                "symbol": ticker,
            })
            current_price = 0.0
            if price_data and "Global Quote" in price_data:
                gq = price_data["Global Quote"]
                current_price = float(gq.get("05. price", 0))

            info = {
                "ticker":          ticker,
                "name":            data.get("Name", ""),
                "sector":          data.get("Sector", ""),
                "industry":        data.get("Industry", ""),
                "market_cap":      int(float(data.get("MarketCapitalization", 0))),
                "current_price":   current_price,
                "pe_ratio":        _safe_float(data.get("TrailingPE")),
                "forward_pe":      _safe_float(data.get("ForwardPE")),
                "peg_ratio":       _safe_float(data.get("PEGRatio")),
                "dividend_yield":  _safe_float(data.get("DividendYield")),
                "beta":            _safe_float(data.get("Beta")),
                "avg_volume":      int(float(data.get("AverageVolume", 0) or 0)),
                "avg_volume_10d":  int(float(data.get("AverageVolume10Day", 0) or 0)),
                "52w_high":        _safe_float(data.get("52WeekHigh")),
                "52w_low":         _safe_float(data.get("52WeekLow")),
                "50d_avg":         _safe_float(data.get("50DayMovingAverage")),
                "200d_avg":        _safe_float(data.get("200DayMovingAverage")),
                "exchange":        data.get("Exchange", ""),
                "currency":        data.get("Currency", "USD"),
                "eps":             _safe_float(data.get("EPS")),
                "book_value":      _safe_float(data.get("BookValue")),
                "profit_margin":   _safe_float(data.get("ProfitMargin")),
                "revenue_growth":  _safe_float(data.get("QuarterlyRevenueGrowthYOY")),
            }

            _fundamental_cache[ticker] = info
            log_info(MODULE, f"Fetched fundamentals for {ticker}: "
                             f"Cap={info['market_cap']:,} | P/E={info['pe_ratio']} | "
                             f"Price=${info['current_price']:.2f}")
            return info

        except Exception as e:
            log_error(MODULE, f"Error getting info for {ticker}: {e}")
            return None

    # ── Current Price (fast) ───────────────────────────

    async def get_current_price(self, ticker: str) -> float:
        """Get current price via GLOBAL_QUOTE (1 API call)."""
        try:
            data = self._request({
                "function": "GLOBAL_QUOTE",
                "symbol": ticker,
            })
            if data and "Global Quote" in data:
                return float(data["Global Quote"].get("05. price", 0))
            return 0.0
        except:
            return 0.0

    # ── Multiple Tickers ──────────────────────────────

    async def get_multiple_tickers(
        self,
        tickers: list[str],
        interval: str = "15m",
        period: str = "5d",
    ) -> dict[str, pd.DataFrame]:
        """Download OHLCV for multiple tickers. Returns dict ticker -> DataFrame."""
        results = {}
        for ticker in tickers:
            df = await self.get_ohlcv(ticker, interval=interval, period=period)
            if df is not None and not df.empty:
                results[ticker] = df
        return results

    # ── Hard Filters ──────────────────────────────────

    def apply_hard_filters(
        self,
        info: dict,
        max_price: float = 300.0,
        min_volume: int = 700_000,
        min_market_cap: int = 500_000_000,
    ) -> bool:
        """
        Apply hard filters to a stock candidate.
        Returns True if stock passes ALL filters.
        """
        price = info.get("current_price", 0)
        volume = info.get("avg_volume", 0)
        market_cap = info.get("market_cap", 0)

        # Price filter: $1 - $max_price
        if not (1.0 <= price <= max_price):
            return False

        # Volume filter
        if volume < min_volume:
            return False

        # Market cap filter
        if market_cap < min_market_cap:
            return False

        return True


def _safe_float(val) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if val is None or val == "None" or val == "-" or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
