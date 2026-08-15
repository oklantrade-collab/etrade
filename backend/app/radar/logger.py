"""
Logging utilities for RADAR module.
eTrade v5.0
"""
import numpy as np
import pandas as pd
from typing import Any, Dict
from app.core.logger import log_info, log_error, log_warning
from app.radar.config import MODULE


def _sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitizes objects for JSON serialization,
    converting NumPy types, Pandas types, NaNs, and Infs.
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


def log_radar_event(symbol: str, event: Dict[str, Any]) -> None:
    """
    Logs a discrete RADAR event to the system logs.
    """
    try:
        sanitized = _sanitize_for_json(event)
        ev_type = sanitized.get('event_type', 'UNKNOWN')
        direction = sanitized.get('direction', '')
        detail = sanitized.get('detail', '')
        log_info(MODULE, f"[{symbol}] EVENT: {ev_type} ({direction}) — {detail}")
    except Exception as e:
        log_error(MODULE, f"Error logging radar event: {e}")
