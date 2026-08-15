import math
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.rebote_aduana.config import MODULE

def _sanitize_for_json(obj: Any) -> Any:
    """Recursively sanitize numpy types, NaN/Inf, and non-serializable objects for JSON / Supabase."""
    if obj is None:
        return None
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, np.ndarray):
        return [_sanitize_for_json(x) for x in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize_for_json(x) for x in obj]
    if pd.isna(obj):
        return None
    return obj

def log_rebote_score(
    symbol: str,
    result: 'ReboteResult'
) -> None:
    """Logs REBOTE evaluation to rebote_scores_log table and system logs."""
    try:
        supabase = get_supabase()
        raw_data = {
            'symbol': symbol,
            'direction': result.direction,
            'score_raw': result.score_raw,
            'score_final': result.score_final,
            'decision': result.decision,
            'regime_adx': result.regime_adx,
            'regime_local': result.regime_local,
            'contra_trend': result.contra_trend,
            'contra_trend_confirmed': result.contra_trend_confirmed,
            'volume_confirmed': result.volume_confirmed,
            'fib_zone': result.fib_zone,
            'signals': result.signals,
            'detail': result.detail,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        data = _sanitize_for_json(raw_data)
        
        supabase.table('rebote_scores_log').insert(data).execute()
        
        log_info(
            MODULE,
            f"REBOTE Score | {symbol} | Dir: {result.direction} | Final: {result.score_final} | Decision: {result.decision}",
            context=data
        )
    except Exception as e:
        log_error(MODULE, f"Error logging REBOTE score: {str(e)}")

def log_aduana_decision(
    symbol: str,
    side: str,
    order_type: str,
    result: 'AduanaResult',
    strategy: str = ''
) -> None:
    """Logs ADUANA validation to aduana_decisions_log table and system logs."""
    try:
        supabase = get_supabase()
        raw_data = {
            'symbol': symbol,
            'side': side,
            'order_type': order_type,
            'strategy_source': strategy,
            'approved': result.approved,
            'rule_triggered': result.rule_triggered,
            'step': result.step,
            'reason': result.reason,
            'detail': result.detail,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        data = _sanitize_for_json(raw_data)
        
        supabase.table('aduana_decisions_log').insert(data).execute()
        
        if result.approved:
            log_info(
                MODULE,
                f"ADUANA Approved | {symbol} | Side: {side} | Step: {result.step}",
                context=data
            )
        else:
            log_warning(
                MODULE,
                f"ADUANA Rejected | {symbol} | Side: {side} | Rule: {result.rule_triggered} | Reason: {result.reason}",
                context=data
            )
    except Exception as e:
        log_error(MODULE, f"Error logging ADUANA decision: {str(e)}")
