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
            'direction': detail.get('direction', 'LONG') if detail else 'LONG',
            'score_1d': scores_by_layer.get('1d', 0),
            'score_4h': scores_by_layer.get('4h', 0),
            'score_15m': scores_by_layer.get('15m', 0),
            'score_5m': scores_by_layer.get('5m', 0),
            'score_1m': scores_by_layer.get('1m', 0),
            'rsi_adj_1d': detail.get('rsi_adj_1d', 0) if detail else 0,
            'rsi_adj_4h': detail.get('rsi_adj_4h', 0) if detail else 0,
            'rsi_adj_15m': detail.get('rsi_adj_15m', 0) if detail else 0,
            'rsi_adj_5m': detail.get('rsi_adj_5m', 0) if detail else 0,
            'regime': detail.get('regime', 'neutral') if detail else 'neutral',
            'regime_adx': detail.get('regime_adx', 1.0) if detail else 1.0,
            'compression_index': detail.get('compression_index', 0.0) if detail else 0.0,
            'compression_timeframe': detail.get('compression_timeframe', '') if detail else '',
            'score_final': score_final,
            'semaforo': semaforo.value,
            'decision': decision.value,
            'executed': executed,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        supabase.table('halcon_scores_log').insert(data).execute()
        
        log_info(
            MODULE,
            f"HALCON Score | {symbol} | Pos: {position_id} | Final: {score_final} | Semaforo: {semaforo.value} | Decision: {decision.value}",
            context=data
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
            MODULE,
            f"Centinela Decision | {symbol} | Pos: {position_id} | Decision: {decision.value} | PnL: {pnl_at_decision}",
            context=data
        )
    except Exception as e:
        log_error(f"Error logging Centinela decision: {str(e)}", MODULE)
