"""
eTrader v2 — MTF Scorer
Multi-Timeframe scoring engine — the heart of the decision system.
Evaluates 6 timeframes with weighted votes to produce a final score.
"""
from app.core.config import MTF_WEIGHTS
from app.core.logger import log_info, log_debug, log_warning

MODULE = "mtf_scoring"


def evaluate_timeframe(indicators: dict) -> dict:
    """
    Evaluate a single timeframe with 5 conditions.
    Each condition votes +1 (bullish), -1 (bearish), or 0 (neutral).

    Parameters
    ----------
    indicators : dict with keys ema_3, ema_9, ema_20, ema_50,
                 rsi_14, macd_histogram, close

    Returns
    -------
    dict with 'vote' (-1, 0, +1) and 'detail' dict of c1..c5 scores
    """
    ema_3 = indicators.get("ema_3")
    ema_9 = indicators.get("ema_9")
    ema_20 = indicators.get("ema_20")
    ema_50 = indicators.get("ema_50")
    rsi_14 = indicators.get("rsi_14")
    macd_hist = indicators.get("macd_histogram")
    close = indicators.get("close")

    # ── c1: EMA3 vs EMA9 (ultra-fast signal) ──
    c1 = 0
    if ema_3 is not None and ema_9 is not None and ema_9 != 0:
        diff_pct = abs(ema_3 - ema_9) / ema_9
        if diff_pct >= 0.001:
            c1 = 1 if ema_3 > ema_9 else -1

    # ── c2: EMA9 vs EMA20 (fast signal) ──
    c2 = 0
    if ema_9 is not None and ema_20 is not None and ema_20 != 0:
        diff_pct = abs(ema_9 - ema_20) / ema_20
        if diff_pct >= 0.001:
            c2 = 1 if ema_9 > ema_20 else -1

    # ── c3: RSI14 momentum ──
    c3 = 0
    if rsi_14 is not None:
        if rsi_14 > 55:
            c3 = 1
        elif rsi_14 < 45:
            c3 = -1

    # ── c4: MACD histogram direction ──
    c4 = 0
    if macd_hist is not None:
        umbral = 0.0001
        if macd_hist > umbral:
            c4 = 1
        elif macd_hist < -umbral:
            c4 = -1

    # ── c5: Price vs EMA50 (structural position) ──
    c5 = 0
    if close is not None and ema_50 is not None and ema_50 != 0:
        diff_pct = abs(close - ema_50) / ema_50
        if diff_pct >= 0.001:
            c5 = 1 if close > ema_50 else -1

    suma = c1 + c2 + c3 + c4 + c5

    if suma >= 3:
        vote = 1
    elif suma <= -3:
        vote = -1
    else:
        vote = 0

    return {
        "vote": vote,
        "detail": {
            "c1_ema3_vs_ema9": c1,
            "c2_ema9_vs_ema20": c2,
            "c3_rsi": c3,
            "c4_macd_histogram": c4,
            "c5_price_vs_ema50": c5,
            "suma": suma,
        },
    }


def calculate_mtf_score(
    symbol: str,
    all_indicators: dict[str, dict],
    spike_direction: str = "BULLISH",
    cycle_id: str | None = None,
) -> dict:
    """
    Calculate the weighted MTF score across all timeframes.

    Parameters
    ----------
    symbol : str
    all_indicators : dict mapping timeframe → indicator values
        e.g. {'15m': {...}, '30m': {...}, '1h': {...}, '4h': {...}, '1d': {...}, '1w': {...}}
    spike_direction : 'BULLISH' or 'BEARISH'

    Returns
    -------
    dict with keys: score, votes, votes_detail, alignment, timeframes_evaluated
    """
    votes: dict[str, int] = {}
    votes_detail: dict[str, dict] = {}

    for tf in MTF_WEIGHTS:
        if tf not in all_indicators or all_indicators[tf] is None:
            votes[tf] = 0
            votes_detail[tf] = {"vote": 0, "detail": "no_data"}
            continue

        result = evaluate_timeframe(all_indicators[tf])
        votes[tf] = result["vote"]
        votes_detail[tf] = result

    # Weighted score
    score = sum(votes[tf] * MTF_WEIGHTS[tf] for tf in MTF_WEIGHTS)
    score = round(score, 4)

    # Verify alignment with spike direction
    if spike_direction == "BULLISH" and score < 0:
        alignment = "CONTRADICTS_SPIKE"
    elif spike_direction == "BEARISH" and score > 0:
        alignment = "CONTRADICTS_SPIKE"
    else:
        alignment = "ALIGNED"

    if alignment == "CONTRADICTS_SPIKE":
        log_warning(
            MODULE,
            f"{symbol}: MTF score {score:+.4f} CONTRADICTS {spike_direction} spike",
            {"symbol": symbol, "score": score, "spike_direction": spike_direction},
            cycle_id,
        )

    timeframes_evaluated = len([v for v in votes.values() if v != 0])

    result = {
        "score": score,
        "votes": votes,
        "votes_detail": votes_detail,
        "alignment": alignment,
        "timeframes_evaluated": timeframes_evaluated,
    }

    log_info(
        MODULE,
        f"MTF Score for {symbol}: {score:+.4f} | votes: {votes} | alignment: {alignment}",
        {"symbol": symbol, "score": score, "votes": votes, "alignment": alignment},
        cycle_id,
    )

    # Log detailed vote breakdown for auditability
    for tf, detail in votes_detail.items():
        if isinstance(detail, dict) and "detail" in detail and isinstance(detail["detail"], dict):
            d = detail["detail"]
            log_debug(
                MODULE,
                f"  {tf}: vote={votes[tf]:+d} | c1={d.get('c1_ema3_vs_ema9', 0):+d} "
                f"c2={d.get('c2_ema9_vs_ema20', 0):+d} c3={d.get('c3_rsi', 0):+d} "
                f"c4={d.get('c4_macd_histogram', 0):+d} c5={d.get('c5_price_vs_ema50', 0):+d} "
                f"sum={d.get('suma', 0):+d}",
                cycle_id=cycle_id,
            )

    return result
