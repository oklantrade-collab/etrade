"""
eTrader v2 — Technical Indicators Engine
Calculates all technical indicators using the 'ta' package.
Upserts results into Supabase technical_indicators table with retry logic.
"""
import time
import pandas as pd
from ta.trend import EMAIndicator, MACD, ADXIndicator, SMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import VolumeWeightedAveragePrice
from datetime import datetime, timezone
from app.analysis.fibonacci_bb import fibonacci_bollinger, extract_fib_levels

from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_warning, log_error
from app.analysis.data_fetcher import to_internal_symbol

MODULE = "technical_indicators"

# Intraday timeframes that support VWAP
INTRADAY_TIMEFRAMES = {"15m", "30m", "1h", "4h"}


def calculate_indicators(
    df: pd.DataFrame,
    timeframe: str,
    symbol: str | None = None,
) -> dict | None:
    """
    Calculate all technical indicators on a DataFrame.

    Parameters
    ----------
    df : DataFrame with OHLCV data (minimum 50 rows required)
    timeframe : e.g. '15m', '4h', '1d'
    symbol : Binance-format symbol

    Returns
    -------
    dict with all indicator values for the last candle, or None if insufficient data.
    """
    if df is None or df.empty or len(df) < 50:
        if symbol:
            log_warning(
                MODULE,
                f"Insufficient data for {symbol} {timeframe}: "
                f"{len(df) if df is not None else 0} rows (need >= 50)",
            )
        return None

    # Ensure numeric types
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── EMA: 3, 9, 20, 50, 200 ──  (CRÍTICO: ema_3 incluido)
    df["ema_3"] = EMAIndicator(close=df["close"], window=3).ema_indicator()
    df["ema_9"] = EMAIndicator(close=df["close"], window=9).ema_indicator()
    df["ema_20"] = EMAIndicator(close=df["close"], window=20).ema_indicator()
    df["ema_50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
    df["ema_200"] = EMAIndicator(close=df["close"], window=200).ema_indicator()

    # ── RSI 14 ──
    df["rsi_14"] = RSIIndicator(close=df["close"], window=14).rsi()

    # ── MACD (12, 26, 9) ──
    macd = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd_line"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_histogram"] = macd.macd_diff()

    # ── Bollinger Bands (20, 2σ) ──
    bb = BollingerBands(close=df["close"], window=20, window_dev=2)
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_upper"] = bb.bollinger_hband()

    # ── ATR 14 ──
    df["atr_14"] = AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=14
    ).average_true_range()

    # ── ADX 14 ──
    adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=14)
    df["adx_14"] = adx.adx()
    df["di_plus"] = adx.adx_pos()
    df["di_minus"] = adx.adx_neg()

    # ── VWAP (intraday only) ──
    if timeframe in INTRADAY_TIMEFRAMES:
        try:
            vwap = VolumeWeightedAveragePrice(
                high=df["high"], low=df["low"], close=df["close"], volume=df["volume"]
            )
            df["vwap"] = vwap.volume_weighted_average_price()
        except Exception:
            df["vwap"] = None
    else:
        df["vwap"] = None

    # ── Stochastic (14, 3) ──
    stoch = StochasticOscillator(
        high=df["high"], low=df["low"], close=df["close"], window=14, smooth_window=3
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    # ── Williams %R (14) ──
    williams = WilliamsRIndicator(
        high=df["high"], low=df["low"], close=df["close"], lbp=14
    )
    df["williams_r"] = williams.williams_r()

    # ── Volume SMA 20 ── (BASE for volume spike detection)
    df["volume_sma_20"] = SMAIndicator(close=df["volume"], window=20).sma_indicator()

    # ── Fibonacci Bollinger Bands (length=200, mult=3.0) ──
    df = fibonacci_bollinger(df, length=200, mult=3.0)

    # ── Extract last candle values ──
    last = df.iloc[-1]
    indicator_fields = [
        "ema_3", "ema_9", "ema_20", "ema_50", "ema_200",
        "rsi_14",
        "macd_line", "macd_signal", "macd_histogram",
        "bb_upper", "bb_middle", "bb_lower",
        "atr_14",
        "adx_14", "di_plus", "di_minus",
        "vwap",
        "stoch_k", "stoch_d",
        "williams_r",
        "volume_sma_20",
    ]

    result = {}
    for field in indicator_fields:
        val = last.get(field)
        result[field] = float(val) if pd.notna(val) else None

    # Fibonacci results
    fib_levels = extract_fib_levels(df)
    result.update(fib_levels)

    # Add metadata
    result["symbol"] = symbol
    result["timeframe"] = timeframe
    result["timestamp"] = last["open_time"]
    result["close"] = float(last["close"])
    result["open_time"] = last["open_time"]
    result["_df"] = df  # full DataFrame for further analysis

    # Special flag for 4h ATR (used in SL/TP calculation)
    if timeframe == "4h":
        result["is_4h"] = True

    return result


def upsert_indicators(
    indicators: dict,
    symbol: str,
    timeframe: str,
) -> None:
    """Upsert the latest indicator values into Supabase technical_indicators."""
    if not indicators:
        return

    sb = get_supabase()
    internal_sym = to_internal_symbol(symbol) if "/" not in symbol else symbol

    open_time = indicators.get("open_time")
    if hasattr(open_time, "isoformat"):
        ts = open_time.isoformat()
    else:
        ts = str(open_time)

    row = {
        "symbol": internal_sym,
        "timeframe": timeframe,
        "timestamp": ts,
    }

    fields = [
        "ema_3", "ema_9", "ema_20", "ema_50", "ema_200",
        "rsi_14",
        "macd_line", "macd_signal", "macd_histogram",
        "bb_upper", "bb_middle", "bb_lower",
        "atr_14",
        "adx_14", "di_plus", "di_minus",
        "vwap",
        "stoch_k", "stoch_d",
        "williams_r",
        "volume_sma_20",
    ]

    for field in fields:
        val = indicators.get(field)
        # Replace NaN with None before inserting
        if val is not None and pd.notna(val):
            row[field] = float(val)
        else:
            row[field] = None

    for attempt in range(3):
        try:
            sb.table("technical_indicators").upsert(
                row,
                on_conflict="symbol,timeframe,timestamp",
            ).execute()
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
                    f"Indicator upsert failed after 3 attempts for {symbol} {timeframe}: {e}",
                )


def calculate_all_timeframes(
    candles: dict[str, pd.DataFrame],
    symbol: str,
    cycle_id: str | None = None,
) -> dict[str, dict]:
    """
    Calculate indicators for all timeframes of a symbol.

    Parameters
    ----------
    candles : dict mapping timeframe → DataFrame
    symbol : Binance-format symbol (e.g. 'BTCUSDT')

    Returns
    -------
    dict mapping timeframe → indicator values dict
    """
    all_indicators: dict[str, dict] = {}

    for tf, df in candles.items():
        try:
            indicators = calculate_indicators(df.copy(), tf, symbol)
            if indicators:
                upsert_indicators(indicators, symbol, tf)
                # Remove internal _df before storing
                clean = {k: v for k, v in indicators.items() if k != "_df"}
                all_indicators[tf] = clean
                log_info(
                    MODULE,
                    f"Calculated indicators for {symbol} {tf}",
                    {"symbol": symbol, "timeframe": tf},
                    cycle_id,
                )
        except Exception as e:
            log_error(
                MODULE,
                f"Error calculating indicators for {symbol} {tf}: {e}",
                {"symbol": symbol, "timeframe": tf, "error": str(e)},
                cycle_id,
            )

    return all_indicators
