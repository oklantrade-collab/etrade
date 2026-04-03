"""
eTrader v2 — Signal Generator
Combines Volume Spike + MTF Score + Sentiment to produce final trading signals.
"""
from datetime import datetime, timezone

from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_warning

MODULE = "signal_generator"


def generate_signal(
    symbol: str,
    spike: dict,
    mtf_result: dict,
    sentiment: dict,
    all_indicators: dict,
    cycle_id: str | None,
    config: dict,
) -> dict | None:
    """
    Generate a trading signal based on spike + MTF score + sentiment.

    A spike BULLISH can only produce BUY or HOLD.
    A spike BEARISH can only produce SELL or HOLD.

    Parameters
    ----------
    symbol : str
    spike : dict from volume_spike.detect_spike()
    mtf_result : dict from mtf_scorer.calculate_mtf_score()
    sentiment : dict from gemini_sentiment.get_sentiment()
    all_indicators : dict of all timeframe indicators
    cycle_id : current cycle UUID
    config : system_config dict

    Returns
    -------
    dict with signal details, or None if no entry price available
    """
    # ── STEP 1: Calculate final score ──
    score_mtf = mtf_result.get("score", 0.0)
    adjustment = sentiment.get("adjustment", 0.0)
    score_final = round(score_mtf + adjustment, 4)

    # Clamp to [-1.0, +1.0]
    score_final = max(-1.0, min(1.0, score_final))

    # ── STEP 2: Determine signal type ──
    threshold = float(config.get("mtf_signal_threshold", 0.65))
    spike_direction = spike["direction"]  # 'BULLISH' or 'BEARISH'

    # Signal ONLY aligned with spike direction
    if spike_direction == "BULLISH":
        if score_final >= threshold:
            signal_type = "BUY"
        else:
            signal_type = "HOLD"
    elif spike_direction == "BEARISH":
        if score_final <= -threshold:
            signal_type = "SELL"
        else:
            signal_type = "HOLD"
    else:
        signal_type = "HOLD"

    # ── STEP 3: Get entry price and ATR_4h ──
    indicators_4h = all_indicators.get("4h", {})
    atr_4h = indicators_4h.get("atr_14") if isinstance(indicators_4h, dict) else None
    entry_price = all_indicators.get("15m", {}).get("close") if isinstance(all_indicators.get("15m"), dict) else None

    if entry_price is None:
        log_warning(MODULE, f"{symbol}: No entry price available from 15m indicators", cycle_id=cycle_id)
        return None

    # ── STEP 4: Calculate SL and TP ──
    sl_price = 0.0
    tp_price = 0.0
    rr_ratio = 0.0

    if signal_type in ["BUY", "SELL"] and atr_4h is not None:
        sl_mult = float(config.get("sl_multiplier", 2.0))
        rr = float(config.get("rr_ratio", 2.5))

        sl_distance = atr_4h * sl_mult
        tp_distance = sl_distance * rr

        if signal_type == "BUY":
            sl_price = round(entry_price - sl_distance, 8)
            tp_price = round(entry_price + tp_distance, 8)
        elif signal_type == "SELL":
            sl_price = round(entry_price + sl_distance, 8)
            tp_price = round(entry_price - tp_distance, 8)

        rr_ratio = round(rr, 2)

    # ── STEP 5: Build and save signal ──
    votes = mtf_result.get("votes", {})

    signal_data = {
        "spike_id": spike.get("spike_id"),
        "symbol": symbol,
        "signal_type": signal_type,
        "mtf_score": score_mtf,
        "sentiment_adjustment": adjustment,
        "score_final": score_final,
        "vote_15m": votes.get("15m", 0),
        "vote_30m": votes.get("30m", 0),
        "vote_45m": votes.get("1h", 0),  # 1h maps to the 45m slot in DB
        "vote_4h": votes.get("4h", 0),
        "vote_1d": votes.get("1d", 0),
        "vote_1w": votes.get("1w", 0),
        "entry_price": entry_price,
        "stop_loss": sl_price,
        "take_profit": tp_price,
        "atr_4h_used": atr_4h or 0.0,
        "risk_reward_ratio": rr_ratio or 0.0,
        "status": "pending" if signal_type in ["BUY", "SELL"] else "hold",
    }

    # Save to database
    signal_id = _save_signal(signal_data, cycle_id)

    # Update volume_spikes if signal generated
    if signal_type in ["BUY", "SELL"] and spike.get("spike_id"):
        try:
            sb = get_supabase()
            sb.table("volume_spikes").update({
                "resulted_in_signal": True,
                "mtf_score": score_final,
            }).eq("id", spike["spike_id"]).execute()
        except Exception as e:
            log_warning(MODULE, f"Failed to update spike {spike['spike_id']}: {e}", cycle_id=cycle_id)

    log_info(
        MODULE,
        f"Signal for {symbol}: {signal_type} | score_final={score_final:+.4f} "
        f"(mtf={score_mtf:+.4f} + sent={adjustment:+.4f}) "
        f"| threshold=±{threshold} | SL={sl_price} | TP={tp_price}",
        signal_data,
        cycle_id,
    )

    return {
        "signal_id": signal_id,
        "symbol": symbol,
        "signal_type": signal_type,
        "score_final": score_final,
        "entry_price": entry_price,
        "stop_loss": sl_price,
        "take_profit": tp_price,
        "atr_4h_used": atr_4h,
        "rr_ratio": rr_ratio,
        "should_execute": signal_type in ["BUY", "SELL"],
    }


def _save_signal(signal_data: dict, cycle_id: str | None = None) -> str | None:
    """Persist signal to trading_signals. Returns signal id or None."""
    try:
        from app.analysis.data_fetcher import to_internal_symbol

        sym = signal_data["symbol"]
        internal_sym = to_internal_symbol(sym) if "/" not in sym else sym

        row = {**signal_data, "symbol": internal_sym}

        sb = get_supabase()
        result = sb.table("trading_signals").insert(row).execute()
        if result.data:
            return result.data[0]["id"]
    except Exception as e:
        log_warning(MODULE, f"Failed to save signal: {e}", cycle_id=cycle_id)

    return None
