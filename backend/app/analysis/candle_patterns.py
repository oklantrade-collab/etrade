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


from app.candle_signals.candle_patterns import CandlePatternDetector, CandleOHLC

def detect_patterns(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    cycle_id: str | None = None,
) -> list[dict]:
    """
    Detect candlestick patterns using the SIPV (26 patterns).
    Returns a list of pattern dicts compatible with older callers.
    """
    if df is None or len(df) < 5:
        return []

    try:
        # 1. Prepare Data
        last_row = df.iloc[-1]
        history_rows = df.tail(10).iloc[:-1]
        
        current_ohlc = CandleOHLC(
            open=float(last_row['open']),
            high=float(last_row['high']),
            low=float(last_row['low']),
            close=float(last_row['close']),
            volume=float(last_row.get('volume', 0))
        )
        
        history_ohlc = [
            CandleOHLC(
                open=float(r['open']),
                high=float(r['high']),
                low=float(r['low']),
                close=float(r['close']),
                volume=float(r.get('volume', 0))
            )
            for _, r in history_rows.iterrows()
        ]

        # 2. SIPV Detection
        market = "crypto" if "USD" in symbol.upper() else "stocks"
        detector = CandlePatternDetector(market=market)
        vol_sma = df['volume'].tail(20).mean() if 'volume' in df else None
        
        result = detector.evaluate(current_ohlc, history=history_ohlc, volume_sma20=vol_sma)

        # 3. Format result (match legacy list[dict] expectation)
        if result.pattern_id == 0:
            return []

        p_type = "neutral"
        if result.action == "BUY": p_type = "bullish"
        elif result.action == "SELL": p_type = "bearish"
        elif "Alcista" in result.signal: p_type = "bullish"
        elif "Bajista" in result.signal: p_type = "bearish"

        patterns = [{
            "pattern_name": result.pattern_name,
            "pattern_type": p_type,
            "pattern_strength": result.confidence,
            "timestamp": last_row.get("open_time", datetime.now(timezone.utc)),
            "signal": result.signal
        }]

        # 4. Persist to Supabase
        _save_patterns(patterns, symbol, timeframe, cycle_id)
        
        return patterns

    except Exception as e:
        log_warning(MODULE, f"Error in SIPV pattern detection for {symbol}: {e}")
        return []

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
