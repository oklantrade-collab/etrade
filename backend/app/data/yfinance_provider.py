"""
eTrader v4.5 — yfinance Data Provider
Downloads OHLCV data for US stocks via yfinance.
Used for swing trading (historical) and pre-market scans.

For real-time scalping data, use ib_provider.py instead.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase

MODULE = "yfinance_provider"

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    log_warning(MODULE, "yfinance not installed — pip install yfinance")


class YFinanceProvider:
    """
    Provides OHLCV data for US equities via yfinance.
    
    Supports multiple timeframes: 1m, 5m, 15m, 1h, 4h, 1d, 1wk
    Note: Intraday data (< 1d) limited to ~60 days history.
    """

    # yfinance interval mapping
    INTERVAL_MAP = {
        "1m":  "1m",
        "5m":  "5m",
        "15m": "15m",
        "30m": "30m",
        "1h":  "1h",
        "4h":  "4h",    # yfinance doesn't support 4h natively — we resample
        "1d":  "1d",
        "1wk": "1wk",
    }

    # Max history period per interval (yfinance limitations)
    MAX_PERIOD = {
        "1m":  "7d",
        "5m":  "60d",
        "15m": "60d",
        "30m": "60d",
        "1h":  "730d",
        "1d":  "max",
        "1wk": "max",
    }

    def __init__(self):
        if not YFINANCE_AVAILABLE:
            raise RuntimeError("yfinance is not installed")

    async def get_ohlcv(
        self,
        ticker: str,
        interval: str = "5m",
        period: str | None = None,
        limit: int = 200,
    ) -> pd.DataFrame | None:
        """
        Download OHLCV data for a ticker.

        Parameters
        ----------
        ticker   : US stock ticker (e.g. 'AAPL', 'MSFT')
        interval : Candle interval ('5m', '15m', '1h', '1d', etc.)
        period   : yfinance period string (e.g. '5d', '1mo'). Auto if None.
        limit    : Max number of candles to return.

        Returns
        -------
        DataFrame with columns: open_time, open, high, low, close, volume
        """
        try:
            needs_resample = interval == "4h"
            yf_interval = "1h" if needs_resample else self.INTERVAL_MAP.get(interval, interval)

            if period is None:
                period = self.MAX_PERIOD.get(interval, "60d")

            stock = yf.Ticker(ticker)
            hist = stock.history(period=period, interval=yf_interval)

            if hist is None or hist.empty:
                log_warning(MODULE, f"No data returned for {ticker} {interval}")
                return None

            # Standardize column names
            df = hist.reset_index()
            col_map = {
                "Datetime": "open_time",
                "Date": "open_time",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
            df = df.rename(columns=col_map)

            # Ensure open_time is timezone-aware
            if df["open_time"].dt.tz is None:
                df["open_time"] = df["open_time"].dt.tz_localize("UTC")
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

            # Keep only needed columns
            keep_cols = ["open_time", "open", "high", "low", "close", "volume"]
            df = df[[c for c in keep_cols if c in df.columns]]

            # Ensure numeric
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # Trim to limit
            if len(df) > limit:
                df = df.tail(limit).reset_index(drop=True)

            log_info(MODULE, f"Fetched {len(df)} candles for {ticker} {interval}")
            return df

        except Exception as e:
            log_error(MODULE, f"Error fetching {ticker} {interval}: {e}")
            return None

    async def get_ticker_info(self, ticker: str) -> dict | None:
        """
        Get fundamental info for a ticker (market cap, sector, etc.).
        
        Returns a dict with keys like:
        market_cap, sector, industry, current_price, 
        pe_ratio, forward_pe, dividend_yield, etc.
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            return {
                "ticker":          ticker,
                "name":            info.get("shortName", ""),
                "sector":          info.get("sector", ""),
                "industry":        info.get("industry", ""),
                "market_cap":      info.get("marketCap", 0),
                "current_price":   info.get("currentPrice", 0),
                "pe_ratio":        info.get("trailingPE"),
                "forward_pe":      info.get("forwardPE"),
                "peg_ratio":       info.get("pegRatio"),
                "dividend_yield":  info.get("dividendYield"),
                "beta":            info.get("beta"),
                "avg_volume":      info.get("averageVolume", 0),
                "avg_volume_10d":  info.get("averageDailyVolume10Day", 0),
                "52w_high":        info.get("fiftyTwoWeekHigh"),
                "52w_low":         info.get("fiftyTwoWeekLow"),
                "50d_avg":         info.get("fiftyDayAverage"),
                "200d_avg":        info.get("twoHundredDayAverage"),
                "exchange":        info.get("exchange", ""),
                "currency":        info.get("currency", "USD"),
            }
        except Exception as e:
            log_error(MODULE, f"Error getting info for {ticker}: {e}")
            return None

    async def get_multiple_tickers(
        self,
        tickers: list[str],
        interval: str = "5m",
        period: str = "5d",
    ) -> dict[str, pd.DataFrame]:
        """Download OHLCV for multiple tickers. Returns dict ticker -> DataFrame."""
        results = {}
        for ticker in tickers:
            df = await self.get_ohlcv(ticker, interval=interval, period=period)
            if df is not None and not df.empty:
                results[ticker] = df
        return results

    async def get_spy_regime(self) -> dict:
        """
        Check S&P 500 Market Regime using SPY.
        
        Returns:
            {regime: 'bull'|'bear'|'sideways', vix: float, spy_price: float}
        """
        try:
            # Get SPY data
            spy = yf.Ticker("SPY")
            spy_hist = spy.history(period="1y", interval="1d")
            if spy_hist.empty:
                return {"regime": "sideways", "vix": 20.0, "spy_price": 0}

            spy_close = spy_hist["Close"].values.astype(float)
            spy_price = float(spy_close[-1])

            # Calculate MA50 and MA200
            ma50 = float(np.mean(spy_close[-50:])) if len(spy_close) >= 50 else spy_price
            ma200 = float(np.mean(spy_close[-200:])) if len(spy_close) >= 200 else spy_price

            # Get VIX
            vix_ticker = yf.Ticker("^VIX")
            vix_hist = vix_ticker.history(period="5d", interval="1d")
            vix = float(vix_hist["Close"].iloc[-1]) if not vix_hist.empty else 20.0

            # Determine regime
            if spy_price > ma50 and spy_price > ma200 and vix < 18:
                regime = "bull"
            elif spy_price < ma50 and vix > 25:
                regime = "bear"
            else:
                regime = "sideways"

            return {
                "regime":    regime,
                "vix":       round(vix, 2),
                "spy_price": round(spy_price, 2),
                "ma50":      round(ma50, 2),
                "ma200":     round(ma200, 2),
            }

        except Exception as e:
            log_error(MODULE, f"Error getting SPY regime: {e}")
            return {"regime": "sideways", "vix": 20.0, "spy_price": 0}

    def apply_hard_filters(
        self,
        info: dict,
        max_price: float = 50.0,
        min_volume: int = 500_000,
        min_market_cap: int = 300_000_000,
    ) -> bool:
        """
        Apply hard filters to a stock candidate.

        Returns True if stock passes ALL filters.
        """
        price = info.get("current_price", 0)
        volume = info.get("avg_volume", 0)
        market_cap = info.get("market_cap", 0)
        exchange = info.get("exchange", "")

        # Price filter: $1 - $max_price
        if not (1.0 <= price <= max_price):
            return False

        # Volume filter
        if volume < min_volume:
            return False

        # Market cap filter
        if market_cap < min_market_cap:
            return False

        # Exchange filter (NYSE/NASDAQ only)
        valid_exchanges = {"NMS", "NGM", "NYQ", "NAS", "NYSE", "NASDAQ"}
        if exchange and exchange.upper() not in valid_exchanges:
            return False

        return True


async def upsert_market_data_5m(
    ticker: str,
    df: pd.DataFrame,
    rvol_values: pd.Series | None = None,
    slippage_data: dict | None = None,
) -> None:
    """Upsert 5m OHLCV data into market_data_5m table."""
    if df is None or df.empty:
        return

    sb = get_supabase()
    rows = []
    for i, r in df.iterrows():
        ts = r["open_time"]
        if isinstance(ts, pd.Timestamp):
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            ts = ts.isoformat()

        row = {
            "ticker":    ticker,
            "timestamp": ts,
            "open":      float(r["open"]),
            "high":      float(r["high"]),
            "low":       float(r["low"]),
            "close":     float(r["close"]),
            "volume":    int(r["volume"]),
        }

        if rvol_values is not None and i < len(rvol_values):
            row["rvol"] = float(rvol_values.iloc[i]) if pd.notna(rvol_values.iloc[i]) else None

        if slippage_data:
            row["slippage_est"]   = slippage_data.get("slippage_est")
            row["spread_pct"]     = slippage_data.get("spread_pct")
            row["liquidity_score"] = slippage_data.get("liquidity_score")

        rows.append(row)

    try:
        # Batch upsert (last 100 rows max to stay efficient)
        batch = rows[-100:]
        sb.table("market_data_5m").upsert(
            batch, on_conflict="ticker,timestamp"
        ).execute()
        log_info(MODULE, f"Upserted {len(batch)} rows for {ticker}")
    except Exception as e:
        log_error(MODULE, f"Error upserting market_data_5m for {ticker}: {e}")
