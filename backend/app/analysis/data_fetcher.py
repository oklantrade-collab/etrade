"""
eTrader v2 — Data Fetcher
Fetches OHLCV candle data from Binance REST API for 6 timeframes.
Normalises, validates (sanity check) and upserts into Supabase market_candles.
"""
import time
import requests
import pandas as pd
from datetime import datetime, timezone

from app.core.config import settings, TIMEFRAMES, SYMBOL_MAP, EXCLUDED_SYMBOLS
from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_warning, log_error

MODULE = "data_fetcher"

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

# Binance kline interval strings
BINANCE_INTERVALS = {
    "15m": "15m",
    "30m": "30m",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "1d",
    "1w":  "1w",
}

# Timeframe durations in seconds (for closed-candle filtering)
TF_DURATION_SECONDS = {
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h":  60 * 60,
    "4h":  4 * 3600,
    "1d":  24 * 3600,
    "1w":  7 * 24 * 3600,
}


def to_internal_symbol(binance_symbol: str) -> str:
    """Convert Binance symbol format (BTCUSDT) to internal format (BTC/USDT)."""
    # Check SYMBOL_MAP first
    if binance_symbol in SYMBOL_MAP:
        return SYMBOL_MAP[binance_symbol]
    # Fallback: split by known quote currencies
    for quote in ["USDT", "BUSD", "USDC", "BTC", "ETH", "BNB"]:
        if binance_symbol.endswith(quote):
            base = binance_symbol[: -len(quote)]
            return f"{base}/{quote}"
    return binance_symbol


def to_binance_symbol(internal_symbol: str) -> str:
    """Convert internal format BTC/USDT → BTCUSDT."""
    return internal_symbol.replace("/", "")


def fetch_klines(
    symbol: str,
    timeframe: str,
    limit: int,
) -> pd.DataFrame | None:
    """
    Fetch klines from Binance REST API and return a normalised DataFrame.

    Columns: open_time, open, high, low, close, volume, quote_volume,
             trades_count, taker_buy_volume, taker_sell_volume

    Handles HTTP 429 (rate limit) by waiting 10s and retrying once.
    """
    interval = BINANCE_INTERVALS.get(timeframe, timeframe)
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }

    raw = None
    for attempt in range(2):  # max 2 attempts (initial + 1 retry)
        try:
            resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=30)

            if resp.status_code == 429:
                if attempt == 0:
                    log_warning(MODULE, f"Rate limited (429) for {symbol} {timeframe}. Waiting 10s...")
                    time.sleep(10)
                    continue
                else:
                    log_error(MODULE, f"Rate limited (429) on retry for {symbol} {timeframe}. Skipping.")
                    return None

            resp.raise_for_status()
            raw = resp.json()
            break

        except requests.exceptions.RequestException as e:
            if attempt == 0:
                log_warning(MODULE, f"Request error for {symbol} {timeframe}: {e}. Retrying...")
                time.sleep(2)
                continue
            else:
                log_error(MODULE, f"Request failed on retry for {symbol} {timeframe}: {e}")
                return None

    if not raw:
        return None

    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades_count",
        "taker_buy_base_vol", "taker_buy_quote_vol", "ignore",
    ])

    # Convert types
    for col in ["open", "high", "low", "close", "volume", "quote_volume",
                "taker_buy_base_vol", "taker_buy_quote_vol"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["trades_count"] = df["trades_count"].astype(int)

    # Rename & derive
    df.rename(columns={"taker_buy_base_vol": "taker_buy_volume"}, inplace=True)
    df["taker_sell_volume"] = df["volume"] - df["taker_buy_volume"]

    # Convert open_time from ms to datetime
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)

    # Keep only CLOSED candles: open_time < now - timeframe_duration
    tf_secs = TF_DURATION_SECONDS.get(timeframe, 900)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(seconds=tf_secs)
    df = df[df["open_time"] < cutoff].copy()

    # Select final columns
    df = df[
        [
            "open_time", "open", "high", "low", "close", "volume",
            "quote_volume", "trades_count", "taker_buy_volume", "taker_sell_volume",
        ]
    ]

    return df if not df.empty else None


def sanity_check(df: pd.DataFrame, symbol: str, timeframe: str = "15m", cycle_id: str | None = None) -> bool:
    """
    CRITICAL: Discard malicious or heavily manipulated data.
    Threshold scales with timeframe.
    """
    if df is None or df.empty:
        return False

    ranges = (df["high"] - df["low"]) / df["low"]
    max_range = ranges.max()

    thresholds = {
        "15m": 0.20,
        "30m": 0.25,
        "1h": 0.35,
        "4h": 0.60,
        "1d": 1.50,
        "1w": 2.50,
    }
    limit = thresholds.get(timeframe, 0.20)

    if max_range > limit:
        log_warning(
            MODULE,
            f"Sanity check FAILED for {symbol} {timeframe}: max range {max_range:.4f} > {limit}. Discarding.",
            {
                "module": "data_fetcher",
                "symbol": symbol,
                "timeframe": timeframe,
                "reason": "sanity_check_failed",
                "price_change_pct": float(max_range),
            },
            cycle_id,
        )
        return False
    return True


def upsert_candles(
    df: pd.DataFrame,
    symbol: str,
    exchange: str,
    timeframe: str,
) -> int:
    """Upsert candle data into Supabase market_candles. Returns count upserted."""
    if df is None or df.empty:
        return 0

    sb = get_supabase()
    internal_sym = to_internal_symbol(symbol)
    records = []

    for _, row in df.iterrows():
        records.append({
            "symbol": internal_sym,
            "exchange": exchange,
            "timeframe": timeframe,
            "open_time": row["open_time"].isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "quote_volume": float(row["quote_volume"]) if pd.notna(row["quote_volume"]) else None,
            "trades_count": int(row["trades_count"]),
            "taker_buy_volume": float(row["taker_buy_volume"]) if pd.notna(row["taker_buy_volume"]) else None,
            "taker_sell_volume": float(row["taker_sell_volume"]) if pd.notna(row["taker_sell_volume"]) else None,
        })

    # Upsert in batches of 100 with retry (handles Supabase disconnects)
    count = 0
    for i in range(0, len(records), 100):
        batch = records[i : i + 100]
        for attempt in range(3):
            try:
                sb.table("market_candles").upsert(
                    batch,
                    on_conflict="symbol,exchange,timeframe,open_time",
                ).execute()
                count += len(batch)
                break  # success
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** (attempt + 1)  # 2s, 4s
                    log_warning(
                        MODULE,
                        f"Upsert retry {attempt+1}/3 for {symbol} {timeframe}: {e}. "
                        f"Waiting {wait}s...",
                    )
                    time.sleep(wait)
                else:
                    log_error(
                        MODULE,
                        f"Upsert failed after 3 attempts for {symbol} {timeframe}: {e}",
                    )

    return count


def fetch_all_timeframes(
    symbol: str,
    cycle_id: str | None = None,
) -> dict[str, pd.DataFrame] | None:
    """
    Main entry point: fetch all 6 timeframes for a symbol.

    Returns dict mapping timeframe → DataFrame, or None if sanity
    check fails on any timeframe.
    """
    result: dict[str, pd.DataFrame] = {}

    for tf, cfg in TIMEFRAMES.items():
        try:
            df = fetch_klines(symbol, tf, cfg["limit"])

            if df is None or df.empty:
                log_warning(MODULE, f"No data returned for {symbol} {tf}", cycle_id=cycle_id)
                continue

            # Sanity check — skip this timeframe if it fails, but continue others
            if not sanity_check(df, symbol, tf, cycle_id):
                log_warning(
                    MODULE,
                    f"Skipping {symbol} {tf} due to sanity check failure (continuing other timeframes)",
                    cycle_id=cycle_id,
                )
                continue  # Skip this timeframe only, don't discard the whole symbol

            # Upsert to Supabase
            n = upsert_candles(df, symbol, "binance", tf)
            log_info(
                MODULE,
                f"Upserted {n} candles for {symbol} {tf}",
                {"symbol": symbol, "timeframe": tf, "count": n},
                cycle_id,
            )

            result[tf] = df

        except Exception as e:
            log_error(
                MODULE,
                f"Error fetching {symbol} {tf}: {e}",
                {"symbol": symbol, "timeframe": tf, "error": str(e)},
                cycle_id,
            )

    return result if result else None


def get_top_symbols(n: int = 20, excluded: list[str] | None = None, allowed_symbols: list[str] | str | None = None) -> list[str]:
    """
    Retrieve the top N symbols by 24h quote volume from Binance.
    If allowed_symbols is provided, only those are returned.
    Returns symbols in Binance format (e.g. 'BTCUSDT').
    Only USDT pairs. Excludes stablecoins and leveraged tokens.
    """
    if allowed_symbols:
        # If allowed_symbols is active, just return them up to 'n'
        if isinstance(allowed_symbols, str):
            symbols = [s.strip() for s in allowed_symbols.split(",") if s.strip()]
        else:
            symbols = [str(s).strip() for s in allowed_symbols if str(s).strip()]
        
        if len(symbols) > 0:
            return symbols[:n]

    if excluded is None:
        excluded = EXCLUDED_SYMBOLS

    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            timeout=30,
        )
        resp.raise_for_status()
        tickers = resp.json()
    except Exception as e:
        log_error(MODULE, f"Failed to fetch ticker data: {e}")
        return []

    usdt_tickers = [
        t for t in tickers
        if t["symbol"].endswith("USDT")
        and t["symbol"] not in excluded
        and not t["symbol"].endswith("DOWNUSDT")
        and not t["symbol"].endswith("UPUSDT")
        and "BULL" not in t["symbol"]
        and "BEAR" not in t["symbol"]
    ]

    usdt_tickers.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)

    return [t["symbol"] for t in usdt_tickers[:n]]
