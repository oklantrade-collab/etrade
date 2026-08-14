from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.core.logger import log_info, log_error
from app.core.supabase_client import get_supabase
from app.halcon_centinela.config import Semaforo, CentinelaDecision, MODULE

def log_halcon_score(
    position_id: str,
    symbol: str,
    scores_by_layer: Dict[str, float],
    score_final: float,
    semaforo: Semaforo,
    decision: CentinelaDecision,
    executed: bool,
    detail: Optional[Dict[str, Any]] = None
) -> None:
    """
    Logs HALCON evaluation score to Supabase halcon_scores_log and system logs.
    """
    try:
        supabase = get_supabase()
        data = {
            'position_id': position_id,
            'symbol': symbol,
            'scores_by_layer': scores_by_layer,
            'score_final': score_final,
            'semaforo': semaforo.value,
            'decision': decision.value,
            'executed': executed,
            'detail': detail or {},
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        supabase.table('halcon_scores_log').insert(data).execute()
        
        log_info(
            f"HALCON Score | {symbol} | Pos: {position_id} | Final: {score_final} | Semaforo: {semaforo.value} | Decision: {decision.value}",
            MODULE,
            detail=data
        )
    except Exception as e:
        log_error(f"Error logging HALCON score: {str(e)}", MODULE)

def log_centinela_decision(
    position_id: str,
    symbol: str,
    decision: CentinelaDecision,
    reason: str,
    score_final: float,
    pnl_at_decision: float,
    oraculo_override: bool,
    executed: bool,
    execution_result: Optional[Dict[str, Any]] = None
) -> None:
    """
    Logs Centinela decisions to Supabase centinela_decisions_log and system logs.
    """
    try:
        supabase = get_supabase()
        data = {
            'position_id': position_id,
            'symbol': symbol,
            'decision': decision.value,
            'reason': reason,
            'score_final': score_final,
            'pnl_at_decision': pnl_at_decision,
            'oraculo_override': oraculo_override,
            'executed': executed,
            'execution_result': execution_result or {},
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        supabase.table('centinela_decisions_log').insert(data).execute()
        
        log_info(
            f"Centinela Decision | {symbol} | Pos: {position_id} | Decision: {decision.value} | PnL: {pnl_at_decision}",
            MODULE,
            detail=data
        )
    except Exception as e:
        log_error(f"Error logging Centinela decision: {str(e)}", MODULE)
