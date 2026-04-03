"""
eTrader v2 — Signals API endpoints
GET /signals — list trading signals
GET /signals/spikes — list volume spikes
GET /signals/{signal_id}/mtf-detail — detailed MTF breakdown
"""
from fastapi import APIRouter, Query, HTTPException
from app.core.supabase_client import get_supabase
from app.core.config import MTF_WEIGHTS

router = APIRouter()


@router.get("")
def get_signals(
    status: str = Query(default=None),
    symbol: str = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
):
    """Get recent trading signals with optional filters."""
    sb = get_supabase()
    query = (
        sb.table("trading_signals")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .offset(offset)
    )
    if status:
        query = query.eq("status", status)
    if symbol:
        query = query.eq("symbol", symbol)
    result = query.execute()
    return {"signals": result.data}


@router.get("/spikes")
def get_spikes(
    limit: int = Query(default=20, le=200),
):
    """Get detected volume spikes."""
    sb = get_supabase()
    result = (
        sb.table("volume_spikes")
        .select("*")
        .order("detected_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"spikes": result.data}


@router.get("/{signal_id}/mtf-detail")
def get_signal_mtf_detail(signal_id: str):
    """
    Get detailed MTF breakdown for a specific signal.
    Returns votes per timeframe with weights and contributions.
    """
    sb = get_supabase()
    result = (
        sb.table("trading_signals")
        .select("*")
        .eq("id", signal_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal = result.data[0]

    # Build votes breakdown
    # Map vote columns to timeframes
    vote_map = {
        "15m": {"weight": MTF_WEIGHTS.get("15m", 0.35), "vote_col": "vote_15m"},
        "30m": {"weight": MTF_WEIGHTS.get("30m", 0.20), "vote_col": "vote_30m"},
        "1h":  {"weight": MTF_WEIGHTS.get("1h", 0.15), "vote_col": "vote_45m"},
        "4h":  {"weight": MTF_WEIGHTS.get("4h", 0.15), "vote_col": "vote_4h"},
        "1d":  {"weight": MTF_WEIGHTS.get("1d", 0.10), "vote_col": "vote_1d"},
        "1w":  {"weight": MTF_WEIGHTS.get("1w", 0.05), "vote_col": "vote_1w"},
    }

    votes_breakdown = []
    for tf, info in vote_map.items():
        vote = signal.get(info["vote_col"], 0) or 0
        weight = info["weight"]
        contribution = round(vote * weight, 4)

        if vote > 0:
            label = "BULLISH"
        elif vote < 0:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        votes_breakdown.append({
            "timeframe": tf,
            "weight": weight,
            "vote": vote,
            "contribution": contribution,
            "label": label,
        })

    score_mtf = signal.get("mtf_score", 0.0) or 0.0
    sentiment_adj = signal.get("sentiment_adjustment", 0.0) or 0.0
    score_final = signal.get("score_final", 0.0) or 0.0

    return {
        "signal": signal,
        "votes_breakdown": votes_breakdown,
        "score_composition": {
            "technical_score": score_mtf,
            "sentiment_adjustment": sentiment_adj,
            "final_score": score_final,
        },
    }
