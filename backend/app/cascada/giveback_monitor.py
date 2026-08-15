"""
Dynamic Giveback Monitor for CASCADA.
eTrade v5.0 — Spec Section 3.7
"""
from typing import Dict, Any, Optional


def update_pnl_pico(pnl_current: float, pnl_pico: Optional[float]) -> float:
    """
    Updates the historical peak PnL (pnl_pico) for an open position.
    """
    if pnl_pico is None:
        return max(pnl_current, 0.0)
    return max(pnl_current, float(pnl_pico))


def evaluate_giveback(
    pnl_current: float, 
    pnl_pico: Optional[float], 
    threshold_pct: float = 0.50,
    min_peak_usd: float = 2.0  # Only enforce giveback if position reached meaningful profit
) -> Dict[str, Any]:
    """
    Evaluates dynamic giveback rule:
    If pnl_current < (pnl_pico * threshold_pct) AND pnl_pico >= min_peak_usd:
        -> Force TOTAL CLOSE, bypassing cascade_hold.
    
    Returns:
        {
            'triggered': bool,
            'pnl_current': float,
            'pnl_pico': float,
            'giveback_pct': float,
            'floor_pnl': float,
            'detail': str
        }
    """
    current = float(pnl_current)
    peak = float(pnl_pico) if pnl_pico is not None else 0.0

    if peak < min_peak_usd:
        return {
            'triggered': False,
            'pnl_current': current,
            'pnl_pico': peak,
            'giveback_pct': 0.0,
            'floor_pnl': 0.0,
            'detail': f"Peak PnL (${peak:.2f}) below threshold (${min_peak_usd:.2f}) for giveback rule"
        }

    floor_pnl = peak * (1.0 - threshold_pct)
    # Giveback triggered if current PnL fell below 50% of the peak
    triggered = current < floor_pnl

    giveback_pct = ((peak - current) / peak * 100.0) if peak > 0 else 0.0

    return {
        'triggered': triggered,
        'pnl_current': current,
        'pnl_pico': peak,
        'giveback_pct': round(giveback_pct, 2),
        'floor_pnl': round(floor_pnl, 2),
        'detail': (
            f"GIVEBACK TRIGGERED: PnL dropped from ${peak:.2f} to ${current:.2f} "
            f"({giveback_pct:.1f}% giveback, floor: ${floor_pnl:.2f})"
            if triggered else
            f"PnL ${current:.2f} healthy vs peak ${peak:.2f} (floor: ${floor_pnl:.2f})"
        )
    }
