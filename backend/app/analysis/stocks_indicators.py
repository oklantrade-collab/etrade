"""
eTrader v4.5 — Stocks Technical Indicators (TA-Lib)
Calculates all technical indicators for US equities using the 'ta' library.
Generates a Technical Score (0-100) and MTF confirmation status.

Ported from app/analysis/technical_indicators.py (Crypto) with stocks-specific
adaptations: RVOL replaces Crypto volume spike, and MTF includes 1d timeframe.
"""
import pandas as pd
import numpy as np
from typing import Optional

from ta.trend import EMAIndicator, MACD, ADXIndicator, SMAIndicator, PSARIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase

MODULE = "stocks_indicators"

# Stock MTF timeframes (5 timeframes, need 4/5 confirming)
STOCK_TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]


def calculate_stock_indicators(
    df: pd.DataFrame,
    timeframe: str,
    ticker: str | None = None,
) -> dict | None:
    """
    Calculate all technical indicators on a stocks DataFrame.

    Parameters
    ----------
    df        : DataFrame with OHLCV data (minimum 50 rows)
    timeframe : e.g. '5m', '15m', '1h', '4h', '1d'
    ticker    : Stock ticker symbol

    Returns
    -------
    dict with all indicator values for the last candle, or None if insufficient data.
    """
    if df is None or df.empty or len(df) < 50:
        if ticker:
            log_warning(MODULE, f"Insufficient data for {ticker} {timeframe}: "
                                f"{len(df) if df is not None else 0} rows (need >= 50)")
        return None

    # Ensure numeric types
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # ── EMAs ──
    df["ema_9"] = EMAIndicator(close=close, window=9).ema_indicator()
    df["ema_20"] = EMAIndicator(close=close, window=20).ema_indicator()
    df["ema_50"] = EMAIndicator(close=close, window=50).ema_indicator()
    if len(df) >= 200:
        df["ema_200"] = EMAIndicator(close=close, window=200).ema_indicator()
    else:
        df["ema_200"] = None

    # ── RSI 14 ──
    df["rsi_14"] = RSIIndicator(close=close, window=14).rsi()

    # ── MACD (12, 26, 9) ──
    macd = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
    df["macd_line"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_histogram"] = macd.macd_diff()

    # ── Bollinger Bands (20, 2σ) ──
    bb = BollingerBands(close=close, window=20, window_dev=2)
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_upper"] = bb.bollinger_hband()
    # Bollinger Squeeze: bandwidth < threshold
    bandwidth = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
    df["bb_squeeze"] = bandwidth < bandwidth.rolling(20).quantile(0.25)

    # ── ATR 14 ──
    df["atr_14"] = AverageTrueRange(
        high=high, low=low, close=close, window=14
    ).average_true_range()

    # ── ADX 14 ──
    adx = ADXIndicator(high=high, low=low, close=close, window=14)
    df["adx_14"] = adx.adx()
    df["di_plus"] = adx.adx_pos()
    df["di_minus"] = adx.adx_neg()

    # ── Stochastic (14, 3) ──
    stoch = StochasticOscillator(
        high=high, low=low, close=close, window=14, smooth_window=3
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    # ── Parabolic SAR ──
    psar = PSARIndicator(high=high, low=low, close=close, step=0.02, max_step=0.2)
    df["psar"] = psar.psar()
    df["psar_direction"] = np.where(df["psar"] < df["close"], "bullish", "bearish")

    # ── Volume SMA 20 + RVOL ──
    df["volume_sma_20"] = SMAIndicator(close=volume.astype(float), window=20).sma_indicator()
    df["rvol"] = volume / df["volume_sma_20"]

    # ── EMA Alignment ──
    last = df.iloc[-1]
    ema_alignment = _classify_ema_alignment(last)
    df["ema_alignment"] = ema_alignment

    # ── Extract last candle values ──
    indicator_fields = [
        "ema_9", "ema_20", "ema_50", "ema_200",
        "rsi_14",
        "macd_line", "macd_signal", "macd_histogram",
        "bb_upper", "bb_middle", "bb_lower", "bb_squeeze",
        "atr_14",
        "adx_14", "di_plus", "di_minus",
        "stoch_k", "stoch_d",
        "volume_sma_20", "rvol",
        "psar", "psar_direction",
    ]

    result = {}
    for field in indicator_fields:
        val = last.get(field)
        if isinstance(val, (bool, np.bool_)):
            result[field] = bool(val)
        elif isinstance(val, (str, np.str_)):
            result[field] = str(val) # Guardar texto (bullish/bearish) tal cual
        elif pd.notna(val):
            result[field] = float(val)
        else:
            # Fallback for missing EMAs (e.g. new IPOs)
            if field in ["ema_200", "ema_50", "ema_20"]:
                result[field] = float(last["close"]) # Use price as proxy
            else:
                result[field] = None

    result["ticker"] = ticker
    result["timeframe"] = timeframe
    result["close"] = float(last["close"])
    result["volume"] = float(last["volume"])
    result["ema_alignment"] = ema_alignment
    result["_df"] = df  # Full DataFrame for further analysis

    return result


def _classify_ema_alignment(row) -> str:
    """Classify EMA alignment pattern."""
    try:
        close = float(row["close"])
        ema9 = float(row.get("ema_9", 0) or 0)
        ema20 = float(row.get("ema_20", 0) or 0)
        ema50 = float(row.get("ema_50", 0) or 0)

        if ema9 == 0 or ema20 == 0 or ema50 == 0:
            return "unknown"

        # Perfect bullish: close > ema9 > ema20 > ema50
        if close > ema9 > ema20 > ema50:
            return "bullish_perfect"
        elif close > ema20:
            return "bullish"
        # Perfect bearish: close < ema9 < ema20 < ema50
        elif close < ema9 < ema20 < ema50:
            return "bearish_perfect"
        elif close < ema20:
            return "bearish"
        else:
            return "neutral"
    except Exception:
        return "unknown"


def calculate_technical_score(indicators: dict) -> float:
    """
    Generate a Technical Score (0-100) from indicator values.
    
    Components (weight → max contribution):
    - RSI position       (15 pts)
    - MACD signal        (15 pts)
    - ADX strength       (15 pts)
    - EMA alignment      (15 pts)
    - Bollinger position (10 pts)
    - Stochastic         (10 pts)
    - RVOL               (10 pts)
    - DI crossover       (10 pts)
    """
    score = 0.0

    # RSI (15 pts) — oversold=bullish, overbought=signal
    rsi = indicators.get("rsi_14")
    if rsi is not None:
        if 30 <= rsi <= 50:
            score += 15  # Oversold bounce zone
        elif 50 < rsi <= 70:
            score += 12  # Bullish momentum
        elif rsi < 30:
            score += 8   # Deeply oversold — reversal potential
        elif rsi > 70:
            score += 5   # Overbought — caution

    # MACD (15 pts) — crossover and histogram
    macd_hist = indicators.get("macd_histogram")
    if macd_hist is not None:
        if macd_hist > 0:
            score += 15
        elif macd_hist > -0.1:
            score += 8  # Near crossover

    # ADX (15 pts) — trend strength
    adx = indicators.get("adx_14")
    if adx is not None:
        if adx > 30:
            score += 15  # Strong trend
        elif adx > 20:
            score += 10  # Moderate trend
        else:
            score += 5   # Weak/range

    # EMA Alignment (15 pts)
    alignment = indicators.get("ema_alignment", "")
    if alignment == "bullish_perfect":
        score += 15
    elif alignment == "bullish":
        score += 10
    elif alignment == "neutral":
        score += 5

    # Bollinger (10 pts) — squeeze or position
    bb_squeeze = indicators.get("bb_squeeze", False)
    close = indicators.get("close", 0)
    bb_lower = indicators.get("bb_lower")
    if bb_squeeze:
        score += 10  # Squeeze = breakout imminent
    elif bb_lower and close and close <= bb_lower * 1.01:
        score += 8   # Near lower band = support

    # Stochastic (10 pts)
    stoch_k = indicators.get("stoch_k")
    stoch_d = indicators.get("stoch_d")
    if stoch_k is not None and stoch_d is not None:
        if stoch_k < 20:
            score += 10  # Oversold
        elif stoch_k > stoch_d:
            score += 7   # Bullish crossover

    # RVOL (10 pts) — unusual volume
    rvol = indicators.get("rvol")
    if rvol is not None:
        if rvol >= 2.5:
            score += 10  # Volume spike
        elif rvol >= 1.5:
            score += 7
        elif rvol >= 1.0:
            score += 4

    # DI Crossover (10 pts)
    di_plus = indicators.get("di_plus")
    di_minus = indicators.get("di_minus")
    if di_plus is not None and di_minus is not None:
        if di_plus > di_minus:
            score += 10  # Bullish DI crossover

    return min(round(score, 1), 100.0)


def check_mtf_confirmation(
    indicators_by_tf: dict[str, dict],
    required: int = 4,
) -> tuple[bool, int, dict]:
    """
    Check Multi-Timeframe confirmation for stocks.
    
    Parameters
    ----------
    indicators_by_tf : dict mapping timeframe → indicators dict
    required         : Number of TFs that must confirm (default 4 of 5)

    Returns
    -------
    (confirmed: bool, count: int, details: dict)
    """
    confirmations = {}
    bullish_count = 0

    for tf in STOCK_TIMEFRAMES:
        ind = indicators_by_tf.get(tf)
        if ind is None:
            confirmations[tf] = "no_data"
            continue

        # A timeframe confirms bullish if:
        tech_score = calculate_technical_score(ind)
        is_bullish = tech_score >= 55

        confirmations[tf] = {
            "score": tech_score,
            "bullish": is_bullish,
            "ema_alignment": ind.get("ema_alignment", "unknown"),
        }

        if is_bullish:
            bullish_count += 1

    confirmed = bullish_count >= required
    return confirmed, bullish_count, confirmations


def upsert_technical_score(
    ticker: str,
    indicators: dict,
    technical_score: float,
    mtf_confirmed: bool,
) -> None:
    """Upsert technical score into Supabase."""
    try:
        sb = get_supabase()
        from datetime import datetime, timezone

        # Determine MACD signal direction
        macd_hist = indicators.get("macd_histogram", 0)
        macd_signal_dir = "bullish" if (macd_hist or 0) > 0 else "bearish"

        # Determine Fibonacci level
        close = indicators.get("close", 0)
        bb_lower = indicators.get("bb_lower", 0)
        bb_upper = indicators.get("bb_upper", 0)
        if bb_lower and bb_upper and close:
            bb_range = bb_upper - bb_lower
            if bb_range > 0:
                position = (close - bb_lower) / bb_range
                if position <= 0.236:
                    fib_level = "lower_extreme"
                elif position <= 0.382:
                    fib_level = "lower_zone"
                elif position <= 0.618:
                    fib_level = "middle_zone"
                elif position <= 0.764:
                    fib_level = "upper_zone"
                else:
                    fib_level = "upper_extreme"
            else:
                fib_level = "undefined"
        else:
            fib_level = "undefined"

        row = {
            "ticker":            ticker,
            "timestamp":         datetime.now(timezone.utc).isoformat(),
            "rsi_14":            indicators.get("rsi_14"),
            "atr_14":            indicators.get("atr_14"),
            "bollinger_squeeze": indicators.get("bb_squeeze", False),
            "macd_signal":       macd_signal_dir,
            "ema_alignment":     indicators.get("ema_alignment", "unknown"),
            "rvol":              indicators.get("rvol"),
            "fib_level":         fib_level,
            "mtf_confirmed":     mtf_confirmed,
            "technical_score":   technical_score,
            "signals_json":      {
                "price": indicators.get("close"),
                "volume": indicators.get("volume"),
                "rsi": indicators.get("rsi_14"),
                "adx": indicators.get("adx_14"),
                "macd_hist": indicators.get("macd_histogram"),
                "stoch_k": indicators.get("stoch_k"),
                "di_plus": indicators.get("di_plus"),
                "di_minus": indicators.get("di_minus"),
            },
        }

        sb.table("technical_scores").insert(row).execute()
        log_info(MODULE, f"Technical score for {ticker}: {technical_score:.1f} "
                         f"(MTF: {'✅' if mtf_confirmed else '❌'})")

    except Exception as e:
        log_error(MODULE, f"Error upserting technical score for {ticker}: {e}")
