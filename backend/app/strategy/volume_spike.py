"""
eTrader v2 — Volume Spike Detector
Detects abnormal volume spikes on the 15m timeframe and classifies direction.
Always inserts detected spikes into volume_spikes table (including INDETERMINATE).
"""
import pandas as pd
from datetime import datetime, timezone

from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_warning
from app.analysis.data_fetcher import to_internal_symbol

MODULE = "spike_detection"


def detect_spike(
    df_15m: pd.DataFrame,
    indicators_15m: dict,
    config: dict,
    cycle_id: str | None = None,
) -> dict | None:
    """
    Detect a volume spike on the last closed 15m candle.

    Parameters
    ----------
    df_15m : DataFrame of 15m candles
    indicators_15m : dict from technical_indicators.calculate_indicators()
    config : system_config dict (must contain 'spike_multiplier')
    cycle_id : current cycle UUID

    Returns
    -------
    dict with spike info if BULLISH/BEARISH spike detected, or None otherwise.
    Spikes are ALWAYS inserted into volume_spikes table (even INDETERMINATE).
    """
    spike_multiplier = float(config.get("spike_multiplier", 2.5))

    # Get volume SMA 20 from indicators
    volume_sma_20 = indicators_15m.get("volume_sma_20")
    if volume_sma_20 is None or volume_sma_20 == 0:
        return None

    # Last closed candle
    last = df_15m.iloc[-1]
    candle_volume = float(last["volume"])
    candle_open = float(last["open"])
    candle_close = float(last["close"])
    candle_high = float(last["high"])
    candle_low = float(last["low"])
    candle_range = candle_high - candle_low

    # Spike ratio
    spike_ratio = candle_volume / volume_sma_20
    spike_detected = spike_ratio >= spike_multiplier

    if not spike_detected:
        # No spike — return None, no DB insert
        return None

    # ── SPIKE DETECTED — Classify direction ──
    if candle_range == 0:
        direction = "INDETERMINATE"
        body_pct = 0.0
        taker_buy_pct = 50.0
    else:
        body_size = abs(candle_close - candle_open)
        body_pct = body_size / candle_range

        taker_buy_vol = float(last.get("taker_buy_volume", 0))
        total_vol = float(last["volume"])
        taker_buy_pct = (taker_buy_vol / total_vol * 100) if total_vol > 0 else 50.0

        if candle_close > candle_open and body_pct >= 0.30:
            direction = "BULLISH"
        elif candle_close < candle_open and body_pct >= 0.30:
            direction = "BEARISH"
        else:
            direction = "INDETERMINATE"

    # Get timestamp
    timestamp = last["open_time"]
    if hasattr(timestamp, "isoformat"):
        ts_str = timestamp.isoformat()
    else:
        ts_str = str(timestamp)

    # Get symbol name
    symbol = indicators_15m.get("symbol", "UNKNOWN")
    internal_sym = to_internal_symbol(symbol) if "/" not in symbol else symbol

    # ── ALWAYS INSERT into volume_spikes (including INDETERMINATE) ──
    spike_id = _save_spike_to_db(
        symbol=internal_sym,
        detected_at=ts_str,
        candle_open=candle_open,
        candle_close=candle_close,
        candle_volume=candle_volume,
        avg_volume_20=volume_sma_20,
        spike_ratio=round(spike_ratio, 4),
        spike_direction=direction,
        taker_buy_pct=round(taker_buy_pct, 2),
        body_pct=round(body_pct * 100, 2),
        resulted_in_signal=False,
        mtf_score=float(indicators_15m.get('zone', 0)),
        cycle_id=cycle_id,
    )

    log_info(
        MODULE,
        f"SPIKE DETECTED: {direction} | ratio={spike_ratio:.2f}x | "
        f"body={body_pct:.1%} | taker_buy={taker_buy_pct:.1f}%",
        {
            "symbol": internal_sym,
            "direction": direction,
            "spike_ratio": round(spike_ratio, 4),
        },
        cycle_id,
    )

    # ── Return None for INDETERMINATE (spike logged but no signal) ──
    if direction == "INDETERMINATE":
        return None

    # ── Return spike info for BULLISH/BEARISH ──
    return {
        "detected": True,
        "direction": direction,
        "spike_ratio": round(spike_ratio, 4),
        "body_pct": round(body_pct, 4),
        "taker_buy_pct": round(taker_buy_pct, 2),
        "spike_id": spike_id,
        "candle_data": {
            "open": candle_open,
            "close": candle_close,
            "high": candle_high,
            "low": candle_low,
            "volume": candle_volume,
            "timestamp": ts_str,
        },
        "avg_volume_20": round(volume_sma_20, 8),
    }


def _save_spike_to_db(
    symbol: str,
    detected_at: str,
    candle_open: float,
    candle_close: float,
    candle_volume: float,
    avg_volume_20: float,
    spike_ratio: float,
    spike_direction: str,
    taker_buy_pct: float,
    body_pct: float,
    resulted_in_signal: bool,
    mtf_score: float,
    cycle_id: str | None,
) -> str | None:
    """
    Insert a spike record into volume_spikes table.
    Returns the spike UUID or None on failure.
    """
    sb = get_supabase()

    row = {
        "symbol": symbol,
        "detected_at": detected_at,
        "candle_open": candle_open,
        "candle_close": candle_close,
        "candle_volume": candle_volume,
        "avg_volume_20": avg_volume_20,
        "spike_ratio": spike_ratio,
        "spike_direction": spike_direction,
        "taker_buy_pct": taker_buy_pct,
        "body_pct": body_pct,
        "resulted_in_signal": resulted_in_signal,
        "mtf_score": mtf_score,
        "cycle_id": cycle_id,
    }

    try:
        # Use upsert to avoid duplicates if (symbol, detected_at) already exists
        result = sb.table("volume_spikes").upsert(
            row, on_conflict="symbol,detected_at"
        ).execute()
        if result.data:
            return result.data[0]["id"]
    except Exception as e:
        log_warning(MODULE, f"Failed to save spike: {e}", cycle_id=cycle_id)

    return None
