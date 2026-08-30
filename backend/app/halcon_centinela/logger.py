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
    semaforo: Any,
    decision: Any,
    executed: bool,
    detail: Optional[Any] = None
) -> None:
    """
    Logs HALCON evaluation score to Supabase halcon_scores_log and system logs.
    """
    try:
        supabase = get_supabase()
        detail_dict = detail if isinstance(detail, dict) else ({'info': str(detail)} if detail else {})
        semaforo_str = semaforo.value if hasattr(semaforo, 'value') else str(semaforo)
        decision_str = decision.value if hasattr(decision, 'value') else str(decision)
        scores = scores_by_layer if isinstance(scores_by_layer, dict) else {}

        data = {
            'position_id': str(position_id),
            'symbol': symbol,
            'direction': detail_dict.get('direction', 'LONG'),
            'score_1d': scores.get('1d', 0),
            'score_4h': scores.get('4h', 0),
            'score_15m': scores.get('15m', 0),
            'score_5m': scores.get('5m', 0),
            'score_1m': scores.get('1m', 0),
            'rsi_adj_1d': detail_dict.get('rsi_adj_1d', 0),
            'rsi_adj_4h': detail_dict.get('rsi_adj_4h', 0),
            'rsi_adj_15m': detail_dict.get('rsi_adj_15m', 0),
            'rsi_adj_5m': detail_dict.get('rsi_adj_5m', 0),
            'regime': detail_dict.get('regime', 'neutral'),
            'regime_adx': detail_dict.get('regime_adx', 1.0),
            'compression_index': detail_dict.get('compression_index', 0.0),
            'compression_timeframe': detail_dict.get('compression_timeframe', ''),
            'score_final': float(score_final),
            'semaforo': semaforo_str,
            'decision': decision_str,
            'executed': executed,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            supabase.table('halcon_scores_log').insert(data).execute()
        except Exception:
            pass
        
        log_info(
            MODULE,
            f"HALCON Score | {symbol} | Pos: {position_id} | Final: {score_final} | Semaforo: {semaforo_str} | Decision: {decision_str}",
            context=data
        )
    except Exception as e:
        log_error(MODULE, f"Error logging HALCON score: {str(e)}")

def log_centinela_decision(
    position_id: str,
    symbol: str,
    decision: Any,
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
        decision_str = decision.value if hasattr(decision, 'value') else str(decision)
        data = {
            'position_id': str(position_id),
            'symbol': symbol,
            'decision': decision_str,
            'reason': str(reason),
            'score_final': float(score_final),
            'pnl_at_decision': float(pnl_at_decision),
            'oraculo_override': oraculo_override,
            'executed': executed,
            'execution_result': execution_result or {},
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            supabase.table('centinela_decisions_log').insert(data).execute()
        except Exception:
            pass
        
        log_info(
            MODULE,
            f"Centinela Decision | {symbol} | Pos: {position_id} | Decision: {decision_str} | PnL: {pnl_at_decision}",
            context=data
        )
    except Exception as e:
        log_error(MODULE, f"Error logging Centinela decision: {str(e)}")
