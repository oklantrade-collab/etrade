"""
warrior_playbook.py — FastAPI Router for Ross Cameron Experience Knowledge Base.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.stocks.warrior_playbook_engine import warrior_playbook

router = APIRouter(prefix="/api/v1/playbook", tags=["Warrior Playbook Knowledge Base"])


class LiveEvaluationRequest(BaseModel):
    ticker: str
    price: float
    vwap: float
    sma_200: Optional[float] = None
    change_pct: float = 0.0
    float_shares: Optional[float] = None
    spread_pct: Optional[float] = 0.5
    is_running_up: Optional[bool] = False
    is_consolidating_above_vwap: Optional[bool] = False
    tape_acceleration: Optional[bool] = False


@router.get("/sessions")
def list_playbook_sessions():
    """Retorna todas las sesiones y bitácoras de trading de Ross Cameron almacenadas."""
    return {
        "success": True,
        "count": len(warrior_playbook.get_all_sessions()),
        "sessions": warrior_playbook.get_all_sessions()
    }


@router.get("/archetypes")
def list_archetypes():
    """Retorna el catálogo de arquetipos de patrones cuantitativos."""
    return {
        "success": True,
        "archetypes": warrior_playbook.get_archetypes()
    }


@router.get("/case-study-72k")
def get_case_study_72k():
    """Retorna el desglose táctico y psicológico de la sesión de +$72,872.42 (GEM, SVRE, VWave)."""
    session = warrior_playbook.get_session_by_date("2024-06-28")
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return {
        "success": True,
        "case_study": session
    }


@router.post("/ingest")
def ingest_new_experience(payload: Dict[str, Any]):
    """
    Endpoint del proceso WARRIOR_EXPERIENCE_INGESTOR.
    Permite registrar un nuevo video o caso de estudio de trading para alimentar el robot.
    """
    from app.stocks.warrior_experience_ingestor import ingest_warrior_experience
    res = ingest_warrior_experience(payload)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Error en ingesta"))
    return res


@router.post("/evaluate")
def evaluate_ticker_against_playbook(req: LiveEvaluationRequest):
    """
    Evalúa en caliente un ticker según los patrones de Ross Cameron.
    Indica al robot si debe bloquear el trade (ej. por 200 MA overhead),
    comprar soporte en VWAP, o activar piramidación rápida (Scaling In).
    """
    res = warrior_playbook.evaluate_live_opportunity(req.model_dump())
    return {
        "success": True,
        "ticker": req.ticker.upper(),
        "evaluation": {
            "matched": res.matched,
            "archetype_code": res.archetype_code,
            "archetype_name": res.archetype_name,
            "similarity_score": res.similarity_score,
            "action_type": res.action_type,
            "recommended_action": res.recommended_action,
            "historical_trade_ref": res.historical_trade_ref,
            "reasoning": res.reasoning,
            "execution_params": res.execution_params,
            "lessons_learned": res.lessons_learned
        }
    }
