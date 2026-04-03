"""
eTrader v2 — Candle Pattern Detection
Detects candlestick patterns: Doji, Hammer, Shooting Star,
Engulfing, Morning/Evening Star on the last 3 candles.
"""
import pandas as pd
from datetime import datetime, timezone

from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_warning
from app.analysis.data_fetcher import to_internal_symbol

MODULE = "candle_patterns"


def _vela_info(c: pd.Series) -> dict:
    """Calculate body, range, shadows and direction for a candle."""
    body = abs(c["close"] - c["open"])
    rango = c["high"] - c["low"]
    body_pct = body / rango if rango > 0 else 0
    es_alcista = c["close"] > c["open"]
    mecha_sup = c["high"] - max(c["open"], c["close"])
    mecha_inf = min(c["open"], c["close"]) - c["low"]
    return {
        "body": body,
        "rango": rango,
        "body_pct": body_pct,
        "es_alcista": es_alcista,
        "mecha_sup": mecha_sup,
        "mecha_inf": mecha_inf,
    }


def detect_patterns(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    cycle_id: str | None = None,
) -> list[dict]:
    """
    Detect candlestick patterns on the last 3 candles.

    Requires minimum 3 candles. Returns a list of pattern dicts.
    """
    if df is None or len(df) < 3:
        return []

    patterns = []

    c3 = df.iloc[-3]  # oldest of the 3
    c2 = df.iloc[-2]  # middle
    c1 = df.iloc[-1]  # most recent (just closed)

    v1 = _vela_info(c1)
    v2 = _vela_info(c2)
    v3 = _vela_info(c3)

    # Avoid division by zero
    if v1["rango"] == 0:
        return []

    # ── DOJI ──
    if v1["body_pct"] < 0.10:
        patterns.append({
            "pattern_name": "Doji",
            "pattern_type": "neutral",
            "pattern_strength": 60,
            "timestamp": c1.get("open_time"),
        })

    # ── HAMMER (bullish reversal) ──
    if (
        not v1["es_alcista"]
        and v1["mecha_inf"] >= 2 * v1["body"]
        and v1["mecha_sup"] <= 0.2 * v1["rango"]
        and 0.10 <= v1["body_pct"] <= 0.40
    ):
        patterns.append({
            "pattern_name": "Hammer",
            "pattern_type": "bullish",
            "pattern_strength": 75,
            "timestamp": c1.get("open_time"),
        })

    # ── SHOOTING STAR (bearish reversal) ──
    if (
        v1["mecha_sup"] >= 2 * v1["body"]
        and v1["mecha_inf"] <= 0.2 * v1["rango"]
        and 0.10 <= v1["body_pct"] <= 0.40
    ):
        patterns.append({
            "pattern_name": "Shooting Star",
            "pattern_type": "bearish",
            "pattern_strength": 75,
            "timestamp": c1.get("open_time"),
        })

    # ── BULLISH ENGULFING ──
    if (
        not v2["es_alcista"]
        and v1["es_alcista"]
        and c1["open"] < c2["close"]
        and c1["close"] > c2["open"]
        and v1["body"] > v2["body"]
    ):
        patterns.append({
            "pattern_name": "Bullish Engulfing",
            "pattern_type": "bullish",
            "pattern_strength": 85,
            "timestamp": c1.get("open_time"),
        })

    # ── BEARISH ENGULFING ──
    if (
        v2["es_alcista"]
        and not v1["es_alcista"]
        and c1["open"] > c2["close"]
        and c1["close"] < c2["open"]
        and v1["body"] > v2["body"]
    ):
        patterns.append({
            "pattern_name": "Bearish Engulfing",
            "pattern_type": "bearish",
            "pattern_strength": 85,
            "timestamp": c1.get("open_time"),
        })

    # ── MORNING STAR (3-candle bullish reversal) ──
    if (
        not v3["es_alcista"]
        and v2["body_pct"] < 0.20
        and v1["es_alcista"]
        and c1["close"] > (c3["open"] + c3["close"]) / 2
    ):
        patterns.append({
            "pattern_name": "Morning Star",
            "pattern_type": "bullish",
            "pattern_strength": 90,
            "timestamp": c1.get("open_time"),
        })

    # ── EVENING STAR (3-candle bearish reversal) ──
    if (
        v3["es_alcista"]
        and v2["body_pct"] < 0.20
        and not v1["es_alcista"]
        and c1["close"] < (c3["open"] + c3["close"]) / 2
    ):
        patterns.append({
            "pattern_name": "Evening Star",
            "pattern_type": "bearish",
            "pattern_strength": 90,
            "timestamp": c1.get("open_time"),
        })

    # ── Persist to Supabase ──
    if patterns:
        _save_patterns(patterns, symbol, timeframe, cycle_id)

    return patterns


def _save_patterns(
    patterns: list[dict],
    symbol: str,
    timeframe: str,
    cycle_id: str | None,
):
    sb = get_supabase()
    internal_sym = to_internal_symbol(symbol) if "/" not in symbol else symbol

    for p in patterns:
        ts = p.get("timestamp")
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else datetime.now(timezone.utc).isoformat()

        row = {
            "symbol": internal_sym,
            "timeframe": timeframe,
            "pattern_name": p["pattern_name"],
            "pattern_type": p["pattern_type"],
            "pattern_strength": float(p["pattern_strength"]),
            "timestamp": ts_str,
        }
        try:
            sb.table("candle_patterns").insert(row).execute()
            log_info(
                MODULE,
                f"Pattern detected: {p['pattern_name']} ({p['pattern_type']}) "
                f"for {symbol} {timeframe} | strength={p['pattern_strength']}",
                {"symbol": symbol, "pattern": p["pattern_name"]},
                cycle_id,
            )
        except Exception:
            pass  # Duplicate or transient error — not critical
