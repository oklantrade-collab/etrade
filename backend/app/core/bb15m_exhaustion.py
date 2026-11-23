"""
Post-Bollinger 15m Exhaustion Exit Evaluator (Stocks & Options, Blindaje V3).

Liquidates 100% of a position without waiting until 15:00 ET when price on the 15m
timeframe has broken outside its Bollinger Band (Upper BB for CALL/LONG, Lower BB
for PUT/SHORT) and subsequently stalls laterally or reverses.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import pandas as pd


def _get_col(df: pd.DataFrame, name: str) -> Optional[pd.Series]:
    if df is None or not hasattr(df, "columns"):
        return None
    for candidate in (name, name.capitalize(), name.upper(), name.lower()):
        if candidate in df.columns:
            return pd.to_numeric(df[candidate], errors="coerce").astype(float)
    return None


def evaluate_bb15m_post_breakout_exhaustion(
    df_15m: Optional[pd.DataFrame],
    is_bullish: bool,
    state: Optional[Dict[str, Any]] = None,
    current_price: Optional[float] = None,
    position_age_minutes: float = 0.0,
    asset_type: str = "option",
) -> Dict[str, Any]:
    """Evaluate 15m post-Bollinger-breakout lateralization or reversal.

    Persists breakout flags in the returned ``state`` dict:
      - ``bb15m_upper_breakout_seen`` (bullish: CALL / LONG stock)
      - ``bb15m_lower_breakout_seen`` (bearish: PUT / SHORT stock)
    """
    st: Dict[str, Any] = dict(state or {})
    rule_code = "OPT_BB15M_EXHAUSTION_EXIT" if str(asset_type).lower() == "option" else "STK_BB15M_EXHAUSTION_EXIT"

    no_exit = {
        "should_exit": False,
        "rule_code": None,
        "reason": None,
        "exit_ratio": 0.0,
        "state": st,
    }

    if df_15m is None or len(df_15m) < 21:
        return no_exit

    c = _get_col(df_15m, "close")
    h = _get_col(df_15m, "high")
    l = _get_col(df_15m, "low")
    o = _get_col(df_15m, "open")
    if c is None or h is None or l is None or o is None:
        return no_exit

    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std().fillna(0.0)
    bb_upper = sma20 + (2.0 * std20)
    bb_lower = sma20 - (2.0 * std20)

    # Inspect the last 2 closed candles [-3:-1] plus current [-1] for breakout detection
    n = len(c)
    curr_idx = n - 1
    prev_idx = n - 2
    prior_start = max(19, n - 3)

    open_curr = float(o.iloc[curr_idx])
    high_curr = float(h.iloc[curr_idx])
    low_curr = float(l.iloc[curr_idx])
    close_curr = float(c.iloc[curr_idx])
    close_prev = float(c.iloc[prev_idx])
    high_prev = float(h.iloc[prev_idx])
    low_prev = float(l.iloc[prev_idx])
    cur_px = float(current_price) if (current_price is not None and float(current_price) > 0.0) else close_curr

    if is_bullish:
        prior_breakout = any(
            (not pd.isna(bb_upper.iloc[i]))
            and (float(h.iloc[i]) > float(bb_upper.iloc[i]) or float(c.iloc[i]) > float(bb_upper.iloc[i]))
            for i in range(prior_start, n - 1)
        )
        curr_bb_u = float(bb_upper.iloc[curr_idx]) if not pd.isna(bb_upper.iloc[curr_idx]) else 0.0
        curr_breakout = curr_bb_u > 0.0 and (high_curr > curr_bb_u or close_curr > curr_bb_u or cur_px > curr_bb_u)

        previously_seen = bool(st.get("bb15m_upper_breakout_seen", False))
        if previously_seen or prior_breakout or curr_breakout:
            st["bb15m_upper_breakout_seen"] = True
            prev_hi = float(st.get("bb15m_breakout_bar_high") or 0.0)
            st["bb15m_breakout_bar_high"] = round(max(prev_hi, high_curr, high_prev), 4)

        if not st.get("bb15m_upper_breakout_seen") or position_age_minutes < 5.0:
            return no_exit

        # If current bar itself is the sole fresh breakout and is strongly expanding upward, let it run
        if not previously_seen and not prior_breakout and curr_breakout:
            strong_push = (
                close_curr > open_curr
                and close_prev > 0.0
                and close_curr > close_prev * 1.0015
                and cur_px >= close_curr
                and high_curr > high_prev * 1.001
            )
            if strong_push:
                return no_exit

        lateral_stall = (
            high_curr <= high_prev * 1.001
            and close_prev > 0.0
            and ((close_curr - close_prev) / close_prev) <= 0.0015
        )
        is_exhausted = (
            close_curr <= close_prev
            or close_curr < open_curr
            or cur_px < close_prev
            or lateral_stall
        )
        if not is_exhausted:
            return no_exit

        detail_parts = []
        if close_curr <= close_prev:
            detail_parts.append(f"close15m ${close_curr:.2f} <= prev ${close_prev:.2f}")
        elif cur_px < close_prev:
            detail_parts.append(f"precio ${cur_px:.2f} < close15m previo ${close_prev:.2f}")
        elif close_curr < open_curr:
            detail_parts.append("vela roja de rechazo tras ruptura BB_Upper 15m")
        else:
            detail_parts.append("lateralización sin expansión tras ruptura BB_Upper 15m")

        return {
            "should_exit": True,
            "rule_code": rule_code,
            "exit_ratio": 1.0,
            "reason": f"Agotamiento Post-Bollinger 15m ({'; '.join(detail_parts)}). Liquidación 100% inmediata.",
            "state": st,
        }

    # Bearish mirror (PUT / SHORT stock)
    prior_breakout = any(
        (not pd.isna(bb_lower.iloc[i]))
        and (float(l.iloc[i]) < float(bb_lower.iloc[i]) or float(c.iloc[i]) < float(bb_lower.iloc[i]))
        for i in range(prior_start, n - 1)
    )
    curr_bb_l = float(bb_lower.iloc[curr_idx]) if not pd.isna(bb_lower.iloc[curr_idx]) else 0.0
    curr_breakout = curr_bb_l > 0.0 and (low_curr < curr_bb_l or close_curr < curr_bb_l or cur_px < curr_bb_l)

    previously_seen = bool(st.get("bb15m_lower_breakout_seen", False))
    if previously_seen or prior_breakout or curr_breakout:
        st["bb15m_lower_breakout_seen"] = True
        prev_lo = float(st.get("bb15m_breakout_bar_low") or 0.0)
        cand_lo = min(low_curr, low_prev)
        st["bb15m_breakout_bar_low"] = round(min(prev_lo, cand_lo) if prev_lo > 0.0 else cand_lo, 4)

    if not st.get("bb15m_lower_breakout_seen") or position_age_minutes < 5.0:
        return no_exit

    # If current bar itself is the sole fresh breakdown and is strongly expanding downward, hold
    if not previously_seen and not prior_breakout and curr_breakout:
        strong_drop = (
            close_curr < open_curr
            and close_prev > 0.0
            and close_curr < close_prev * 0.9985
            and cur_px <= close_curr
            and low_curr < low_prev * 0.999
        )
        if strong_drop:
            return no_exit

    lateral_stall = (
        low_curr >= low_prev * 0.999
        and close_prev > 0.0
        and ((close_prev - close_curr) / close_prev) <= 0.0015
    )
    is_exhausted = (
        close_curr >= close_prev
        or close_curr > open_curr
        or cur_px > close_prev
        or lateral_stall
    )
    if not is_exhausted:
        return no_exit

    detail_parts = []
    if close_curr >= close_prev:
        detail_parts.append(f"close15m ${close_curr:.2f} >= prev ${close_prev:.2f}")
    elif cur_px > close_prev:
        detail_parts.append(f"precio ${cur_px:.2f} > close15m previo ${close_prev:.2f}")
    elif close_curr > open_curr:
        detail_parts.append("vela verde de giro tras ruptura BB_Lower 15m")
    else:
        detail_parts.append("lateralización sin nuevo mínimo tras ruptura BB_Lower 15m")

    return {
        "should_exit": True,
        "rule_code": rule_code,
        "exit_ratio": 1.0,
        "reason": f"Agotamiento Post-Bollinger 15m Bajista ({'; '.join(detail_parts)}). Liquidación 100% inmediata.",
        "state": st,
    }
