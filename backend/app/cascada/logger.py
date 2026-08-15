"""
Logger for CASCADA Decisions and Level Progress.
eTrade v5.0
"""
import numpy as np
import pandas as pd
from typing import Any, Dict
from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.cascada.config import MODULE


def _sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitizes objects for JSON serialization.
    """
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, np.ndarray):
        return [_sanitize_for_json(x) for x in obj.tolist()]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(x) for x in obj]
    return obj


def log_cascada_decision(result: Any) -> None:
    """
    Logs CASCADA evaluation result to cascada_decisions_log table and system logs.
    """
    try:
        sb = get_supabase()
        record = {
            'position_id': str(result.position_id),
            'symbol': str(result.symbol),
            'market_type': getattr(result, 'market_type', 'forex'),
            'cascade_level': int(result.current_level),
            'previous_level': int(result.previous_level) if result.previous_level is not None else None,
            'level_advanced': bool(result.level_advanced),
            'check_type': str(result.check_type),
            'decision': str(result.decision),
            'cascade_hold': bool(result.cascade_hold),
            'pnl_current': float(result.pnl_current) if result.pnl_current is not None else 0.0,
            'pnl_pico': float(result.pnl_pico) if result.pnl_pico is not None else 0.0,
            'giveback_pct': float(result.giveback_pct) if result.giveback_pct is not None else 0.0,
            'signals': _sanitize_for_json(result.signals),
            'slope_table': _sanitize_for_json(result.slope_table),
            'detail': str(result.detail)
        }

        # Fire and forget DB insertion
        sb.table('cascada_decisions_log').insert(record).execute()

        log_info(
            MODULE,
            f"[{result.symbol}] Pos {result.position_id[:8]}: "
            f"N{result.current_level} -> {result.decision} (Hold: {result.cascade_hold}, "
            f"PnL: ${result.pnl_current:.2f}/{result.pnl_pico:.2f}) — {result.detail}"
        )
    except Exception as e:
        log_error(MODULE, f"Error saving cascada decision to log: {e}")
