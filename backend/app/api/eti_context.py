"""
eti_context.py — FastAPI Router for ETI Rule Pack Context and Evaluators
======================================================================
Expone el endpoint canónico `/api/eti/v1/context` que entrega el Rule Pack
RP_WARRIOR_MOMENTUM_V1 en memoria inmutable, garantizando la integridad de
las reglas de trading de Ross Cameron antes y durante cada sesión de mercado.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.stocks.warrior_momentum_engine import (
    WarriorRulePackManager,
    TickerMetrics,
    Candle,
    ActiveTrade,
    DailySession,
    evaluate_screener,
    evaluate_bull_flag_trigger,
    evaluate_position_lifecycle,
    check_safety_guardrails,
    build_warrior_signal,
    ETISignalPayload
)

router = APIRouter(prefix="/api/eti/v1", tags=["ETI Rule Pack Context & Evaluators"])


class BullFlagEvalRequest(BaseModel):
    candles_1m: List[Candle]
    current_tick_price: float
    vwap: float
    ema9: float


class SignalGenRequest(BaseModel):
    symbol: str
    trigger_price: float
    technical_stop: float
    relative_volume: float = 6.0
    account_tier: str = "base_tier_usd_2000"


@router.get("/context")
def get_rule_pack_context():
    """
    Retorna el Rule Pack inmutable RP_WARRIOR_MOMENTUM_V1 verificado por SHA-256.
    Este es el esquema que el robot carga en memoria inmutable al iniciar sesión.
    """
    mgr = WarriorRulePackManager.get_instance()
    context = mgr.get_context()
    if not context:
        raise HTTPException(status_code=500, detail="No se pudo cargar el Rule Pack RP_WARRIOR_MOMENTUM_V1")

    return {
        "success": True,
        "is_verified": mgr.is_verified,
        "hash_sha256": mgr.hash_sha256,
        "data": context
    }


@router.get("/context/rules")
def list_rules():
    """Lista las reglas operativas contenidas en el Rule Pack."""
    mgr = WarriorRulePackManager.get_instance()
    rules = mgr.rules
    return {
        "success": True,
        "count": len(rules),
        "rules": rules
    }


@router.get("/context/rules/{rule_code}")
def get_rule_by_code(rule_code: str):
    """Retorna los parámetros cuantitativos de una regla específica."""
    mgr = WarriorRulePackManager.get_instance()
    rule = mgr.get_rule_by_code(rule_code.upper())
    if not rule:
        raise HTTPException(status_code=404, detail=f"Regla {rule_code} no encontrada en el Rule Pack")
    return {
        "success": True,
        "rule": rule
    }


@router.post("/context/evaluate/screener")
def evaluate_screener_endpoint(ticker: TickerMetrics):
    """
    Evalúa si un ticker califica bajo los filtros del pre-trade screener:
    Rango de precio, float <= 20M, RVOL >= 5.0, premarket vol >= 500k, noticia alcista y spread.
    """
    is_tradable = evaluate_screener(ticker)
    return {
        "symbol": ticker.symbol.upper(),
        "is_tradable": is_tradable,
        "metrics": ticker.model_dump()
    }


@router.post("/context/evaluate/bull-flag")
def evaluate_bull_flag_endpoint(req: BullFlagEvalRequest):
    """
    Evalúa la formación técnica de Bull Flag / Micro-Pullback sobre EMA 9 / VWAP.
    Calcula el gatillo New High, profundidad del mástil y stop loss técnico.
    """
    res = evaluate_bull_flag_trigger(
        candles_1m=req.candles_1m,
        current_tick_price=req.current_tick_price,
        vwap=req.vwap,
        ema9=req.ema9
    )
    return {
        "success": True,
        "evaluation": res.model_dump()
    }


@router.post("/context/evaluate/lifecycle")
def evaluate_lifecycle_endpoint(trade: ActiveTrade, current_bid: float = Query(...)):
    """
    Evalúa la posición abierta para ejecutar TP1 (+15c / 50% venta + breakeven stop),
    stop loss técnico inicial o salida del runner cuando pierde la EMA 9 en 1m.
    """
    actions = evaluate_position_lifecycle(trade, current_bid=current_bid)
    return {
        "trade_id": trade.trade_id,
        "symbol": trade.symbol,
        "current_bid": current_bid,
        "actions_required": [a.model_dump() for a in actions]
    }


@router.post("/context/evaluate/guardrails")
def evaluate_guardrails_endpoint(session: DailySession):
    """
    Evalúa los disyuntores de seguridad (Circuit Breakers):
    - 2 pérdidas consecutivas
    - -$150 USD de pérdida diaria máxima
    - Hora límite 11:00 EST
    """
    allowed = check_safety_guardrails(session)
    return {
        "trading_allowed": allowed,
        "session_state": session.model_dump()
    }


@router.post("/context/signal/generate", response_model=ETISignalPayload)
def generate_signal_endpoint(req: SignalGenRequest):
    """Genera el payload canónico ETISignalPayload listo para despacho y ejecución."""
    sig = build_warrior_signal(
        symbol=req.symbol,
        trigger_price=req.trigger_price,
        technical_stop=req.technical_stop,
        relative_volume=req.relative_volume,
        account_tier=req.account_tier
    )
    return sig
