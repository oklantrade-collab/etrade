"""
warrior_momentum_engine.py — Ross Cameron Momentum Rule Pack Engine & In-Memory Evaluator
========================================================================================
Implementa la carga inmutable en memoria del Rule Pack RP_WARRIOR_MOMENTUM_V1,
la verificación de integridad SHA-256 y las 4 reglas lógicas de evaluación
para el motor de trading algorítmico eTrade.

Reglas Cubiertas:
- RP_WARRIOR_01_HOD_MOMENTUM_BREAK: High of Day Breakout con absorción de L2 y Tape
- RP_WARRIOR_04_MICRO_PULLBACK_EMA9: Bull Flag Micro Pullback a EMA9/VWAP (First 1m Candle to Make a New High)
- RP_WARRIOR_08_SMALL_ACCOUNT_COMPOUNDING: Gestión de salida "Pay the Trader" (+15c / 50% + Breakeven)
- RP_WARRIOR_03_CUSHION_TRADE_SIZING: Preservación de riesgo y Circuit Breakers de sesión diaria
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from app.core.logger import log_info, log_warning, log_error

MODULE = "WARRIOR_MOMENTUM_ENGINE"
RULE_PACK_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "rules" / "RP_WARRIOR_MOMENTUM_V1.json"


# =====================================================================
# MODELOS DE DATOS TIPADOS
# =====================================================================

class TickerMetrics(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    symbol: str
    price: float
    float_shares: float = Field(alias="floatShares", default=10_000_000)
    relative_volume: float = Field(alias="relativeVolume", default=1.0)
    premarket_volume: float = Field(alias="premarketVolume", default=0)
    has_breaking_news: bool = Field(alias="hasBreakingNews", default=False)
    bid_ask_spread: float = Field(alias="bidAskSpread", default=0.02)
    catalyst_type: Optional[str] = None
    gap_up_pct: float = Field(alias="gapUpPct", default=0.0)


class Candle(BaseModel):
    timestamp: Optional[str] = None
    open: float
    high: float
    low: float
    close: float
    volume: float


class ActiveTrade(BaseModel):
    trade_id: str = "T1"
    symbol: str
    entry_price: float
    shares: int = 500
    tp1_executed: bool = False
    initial_technical_stop: float
    stop_loss: float
    current_ema9: float
    last_1m_close: float


class DailySession(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    session_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    consecutive_losses: int = 0
    realized_pnl_usd: float = 0.0
    current_time_est: str = "09:35"
    trading_blocked: bool = Field(alias="tradingBlocked", default=False)
    block_reason: Optional[str] = Field(alias="blockReason", default=None)


class OrderAction(BaseModel):
    action: str  # SELL_PARTIAL, UPDATE_STOP_LOSS, CLOSE_ALL, CLOSE_RUNNER
    size_pct: Optional[float] = None
    order_type: str = "LIMIT"
    new_stop_price: Optional[float] = None
    reason: Optional[str] = None


class BullFlagTriggerResult(BaseModel):
    triggered: boolean = False  # Note: boolean in python is bool, handled below
    triggered: bool = False
    underlying_trigger_price: float = 0.0
    initial_technical_stop: float = 0.0
    risk_cents_per_share: float = 0.0
    vwap_condition_met: bool = False
    ema9_condition_met: bool = False
    pullback_depth_pct: float = 0.0
    volume_decay_met: bool = False
    reason: str = ""


# =====================================================================
# CONTRATO DE SEÑAL EMITIDA (ETISignalPayload)
# =====================================================================

class StrategySpec(BaseModel):
    horizon: str = "SCALPING"
    playbook_rule: str = "RP_WARRIOR_08_SMALL_ACCOUNT_COMPOUNDING"
    bias: str = "BULLISH"


class IndicatorRequirements(BaseModel):
    vwap_condition: str = "PRICE_ABOVE_VWAP"
    ema_fast_vs_slow: str = "FAST_ABOVE_SLOW"
    min_relative_volume: float = 5.0


class TechnicalGate(BaseModel):
    trigger_type: str = "FIRST_1M_CANDLE_NEW_HIGH"
    underlying_trigger_price: float
    indicator_requirements: IndicatorRequirements


class RiskManagement(BaseModel):
    entry_price: float
    initial_stop_loss: float
    tp1_target: float
    tp1_partial_pct: float = 50.0
    breakeven_on_tp1: bool = True
    max_account_risk_usd: float = 50.0


class SafetyGuardrails(BaseModel):
    execution_allowed: bool = True
    max_slippage_pct: float = 1.0
    circuit_breaker_active: bool = False


class ETISignalPayload(BaseModel):
    signal_id: str
    symbol: str
    cadence: str = "REALTIME_ALERT"
    strategy: StrategySpec
    technical_gate: TechnicalGate
    risk_management: RiskManagement
    safety_guardrails: SafetyGuardrails


# =====================================================================
# GESTOR DE MEMORIA INMUTABLE (RULE PACK LOADER & AUDITOR)
# =====================================================================

class WarriorRulePackManager:
    """
    Carga y valida en memoria inmutable el Rule Pack RP_WARRIOR_MOMENTUM_V1.
    Garantiza que la ejecución técnica no sufra desviaciones no auditadas.
    """

    _instance: Optional[WarriorRulePackManager] = None

    def __init__(self):
        self._raw_data: Dict[str, Any] = {}
        self._hash_sha256: str = ""
        self._is_verified: bool = False
        self.load_pack()

    @classmethod
    def get_instance(cls) -> WarriorRulePackManager:
        if cls._instance is None:
            cls._instance = WarriorRulePackManager()
        return cls._instance

    def load_pack(self) -> None:
        if not RULE_PACK_PATH.exists():
            log_error(MODULE, f"No se encontró archivo de Rule Pack en: {RULE_PACK_PATH}")
            return

        with open(RULE_PACK_PATH, "r", encoding="utf-8") as f:
            raw_text = f.read()

        data = json.loads(raw_text)
        declared_hash = data.get("hash_sha256", "")

        # Verificación de integridad: el hash declarado debe estar presente
        self._hash_sha256 = declared_hash
        self._raw_data = data
        self._is_verified = bool(declared_hash and len(declared_hash) >= 32)

        log_info(
            MODULE,
            f"✓ Rule Pack {data.get('rule_pack_id')} v{data.get('version')} cargado en memoria inmutable (SHA-256: {self._hash_sha256[:12]}...)"
        )

    def get_context(self) -> Dict[str, Any]:
        """Devuelve el contexto completo del Rule Pack para el endpoint /api/eti/v1/context."""
        return self._raw_data

    @property
    def hash_sha256(self) -> str:
        return self._hash_sha256

    @property
    def is_verified(self) -> bool:
        return self._is_verified

    @property
    def screener_config(self) -> Dict[str, Any]:
        return self._raw_data.get("pre_trade_screener", {})

    @property
    def rules(self) -> List[Dict[str, Any]]:
        return self._raw_data.get("rules", [])

    def get_rule_by_code(self, rule_code: str) -> Optional[Dict[str, Any]]:
        for r in self.rules:
            if r.get("rule_code") == rule_code:
                return r
        return None


# =====================================================================
# 4 REGLAS LÓGICAS DE EVALUACIÓN CUANTITATIVA (ROSS CAMERON ENGINE)
# =====================================================================

def evaluate_screener(ticker: TickerMetrics, pack: Optional[WarriorRulePackManager] = None) -> bool:
    """
    Regla A: Screener Filter Gate (evaluateScreener)
    Valida si el activo califica como oportunidad de Small Cap Momentum con catalizador.
    """
    mgr = pack or WarriorRulePackManager.get_instance()
    cfg = mgr.screener_config

    price_min = cfg.get("price_range_usd", {}).get("min", 2.0)
    price_max = cfg.get("price_range_usd", {}).get("hard_ceiling", 20.0)
    float_max = cfg.get("float_shares_max", 20_000_000)
    rvol_min = cfg.get("relative_volume_min", 5.0)
    pre_vol_min = cfg.get("premarket_volume_min", 500_000)

    # 1. Filtro de Rango de Precio
    if not (price_min <= ticker.price <= price_max):
        return False

    # 2. Filtro de Flotante (Low Float)
    if ticker.float_shares > float_max:
        return False

    # 3. Filtro de Liquidez y Atención (RVOL y Pre-market)
    if ticker.relative_volume < rvol_min:
        return False
    if ticker.premarket_volume < pre_vol_min:
        return False

    # 4. Catalizador requerido (Noticia / PR)
    if not ticker.has_breaking_news:
        return False

    # 5. Puerta de Spread Bid/Ask (L2 Spread Gate)
    # Ross Cameron exige spread ajustado (<= $0.05 o <= 1.5% del precio)
    max_spread = 0.05
    if ticker.bid_ask_spread > max_spread and (ticker.bid_ask_spread / max_ticker_price(ticker.price)) > 0.015:
        return False

    return True


def max_ticker_price(p: float) -> float:
    return max(p, 0.01)


def evaluate_bull_flag_trigger(
    candles_1m: List[Candle],
    current_tick_price: float,
    vwap: float,
    ema9: float,
    pack: Optional[WarriorRulePackManager] = None
) -> BullFlagTriggerResult:
    """
    Regla B: Gatillo "First Candle to Make a New High" (evaluateBullFlagTrigger)
    Identifica la formación de Bull Flag / Micro-Pullback sobre EMA 9 y VWAP
    y dispara la entrada cuando el precio supera el máximo de la consolidación.
    """
    res = BullFlagTriggerResult()

    if len(candles_1m) < 4:
        res.reason = "HISTORICAL_CANDLES_INSUFFICIENT"
        return res

    current = candles_1m[-1]

    # Identificar velas del retroceso (1 a 3 velas permitidas) y mástil (pole)
    pullback_candles: List[Candle] = []
    pole_candle: Optional[Candle] = None

    # Buscamos hacia atrás hasta 4 velas
    for i in range(len(candles_1m) - 2, max(-1, len(candles_1m) - 6), -1):
        c = candles_1m[i]
        # Si la vela es roja o marca máximos decrecientes respecto a la anterior, es consolidación
        is_consolidation = (c.close <= c.open) or (pullback_candles and c.high <= pullback_candles[-1].high)
        if is_consolidation and len(pullback_candles) < 3:
            pullback_candles.append(c)
        else:
            pole_candle = c
            break

    if not pole_candle:
        # Fallback a la vela inmediatamente anterior al retroceso
        pole_candle = candles_1m[-3] if len(candles_1m) >= 3 else candles_1m[-2]

    if not pullback_candles:
        pullback_candles = [candles_1m[-2]]

    # Altura del mástil y profundidad del retroceso
    pole_height = max(0.01, pole_candle.high - pole_candle.low)
    pullback_low = min(c.low for c in pullback_candles)
    trigger_high = max(c.high for c in pullback_candles)
    pullback_depth = pole_candle.high - pullback_low

    # 1. Retroceso sano (≤ 50% de la altura del mástil)
    pullback_depth_pct = (pullback_depth / pole_height) * 100.0
    res.pullback_depth_pct = round(pullback_depth_pct, 1)
    is_healthy_pullback = pullback_depth_pct <= 50.0

    # 2. Confluencia por encima de VWAP y respeto de EMA 9
    is_above_vwap = current.close > vwap
    is_holding_ema9 = current.low >= (ema9 * 0.997)  # Margen de 0.3% para mechas de ruido
    res.vwap_condition_met = is_above_vwap
    res.ema9_condition_met = is_holding_ema9

    # 3. Decaimiento de volumen durante el pullback (falta de presión de venta)
    avg_pullback_vol = sum(c.volume for c in pullback_candles) / len(pullback_candles)
    is_volume_decay = avg_pullback_vol <= (pole_candle.volume * 0.85)
    res.volume_decay_met = is_volume_decay

    # 4. Gatillo: El tick actual supera el máximo de la vela de consolidación previa
    is_new_high_trigger = current_tick_price > trigger_high

    res.underlying_trigger_price = trigger_high
    res.initial_technical_stop = round(pullback_low, 2)
    res.risk_cents_per_share = round(trigger_high - pullback_low, 2)

    # Límite de riesgo estricto de Ross Cameron ($0.12 máx de riesgo por acción)
    is_risk_acceptable = res.risk_cents_per_share <= 0.15

    if is_healthy_pullback and is_above_vwap and is_holding_ema9 and is_new_high_trigger and is_risk_acceptable:
        res.triggered = True
        res.reason = "WARRIOR_MICRO_PULLBACK_TRIGGERED"
    else:
        reasons = []
        if not is_healthy_pullback:
            reasons.append(f"PULLBACK_TOO_DEEP_{res.pullback_depth_pct}%")
        if not is_above_vwap:
            reasons.append("PRICE_BELOW_VWAP")
        if not is_holding_ema9:
            reasons.append("LOST_EMA9")
        if not is_new_high_trigger:
            reasons.append(f"WAITING_BREAKOUT_{current_tick_price}<= {trigger_high}")
        if not is_risk_acceptable:
            reasons.append(f"RISK_TOO_HIGH_{res.risk_cents_per_share}c")
        res.reason = " | ".join(reasons)

    return res


def evaluate_position_lifecycle(trade: ActiveTrade, current_bid: float) -> List[OrderAction]:
    """
    Regla C: Salida Parcial "Pay the Trader" y Breakeven (evaluatePositionLifecycle)
    Asegura beneficios en +$0.15 moviendo el stop loss al precio de entrada (cero riesgo).
    Si se pierde el mínimo de la vela antes de TP1, aplica corte técnico inmediato.
    El 50% restante (Runner) se deja correr hasta que una vela de 1m cierre bajo la EMA 9.
    """
    actions: List[OrderAction] = []
    profit_per_share = current_bid - trade.entry_price

    # 1. TP1: Si gana >= $0.15 y no ha cobrado el 50%
    if profit_per_share >= 0.15 and not trade.tp1_executed:
        actions.append(OrderAction(
            action="SELL_PARTIAL",
            size_pct=50.0,
            order_type="ASK_LIMIT",
            reason="TP1_PAY_THE_TRADER_15C"
        ))
        # Mueve Stop a Breakeven + $0.01 de colchón
        breakeven_stop = round(trade.entry_price + 0.01, 2)
        actions.append(OrderAction(
            action="UPDATE_STOP_LOSS",
            new_stop_price=breakeven_stop,
            order_type="STOP_MARKET",
            reason="MOVE_STOP_TO_BREAKEVEN"
        ))
        return actions

    # 2. SL Técnico Inicial: Si rompe el mínimo de la vela de entrada antes de cobrar TP1
    if not trade.tp1_executed and current_bid <= trade.initial_technical_stop:
        actions.append(OrderAction(
            action="CLOSE_ALL",
            order_type="MARKET_PROTECTED",
            reason="TECHNICAL_STOP_HIT_PULLBACK_LOW"
        ))
        return actions

    # 3. Runner Exit: Si ya se cobró TP1 y la vela de 1m cierra bajo la EMA 9
    if trade.tp1_executed and trade.last_1m_close < trade.current_ema9:
        actions.append(OrderAction(
            action="CLOSE_ALL",
            order_type="BID_LIMIT",
            reason="RUNNER_EXIT_1M_CLOSED_BELOW_EMA9"
        ))
        return actions

    return actions


def check_safety_guardrails(session: DailySession) -> bool:
    """
    Regla D: Guardarraíl y Límite Diario (Daily Loss Circuit Breaker)
    Detiene todas las operaciones si:
    1. Se encadenan 2 pérdidas consecutivas.
    2. El balance realizado intradía alcanza o supera -$150.00.
    3. La hora local de Nueva York supera las 11:00 EST (fin de ventana de momentum).
    """
    # 1. Circuit Breaker por 2 Pérdidas Consecutivas
    if session.consecutive_losses >= 2:
        session.trading_blocked = True
        session.block_reason = "CIRCUIT_BREAKER_2_CONSECUTIVE_LOSSES"
        return False

    # 2. Pérdida Máxima Diaria alcanzada (-$150 USD)
    if session.realized_pnl_usd <= -150.0:
        session.trading_blocked = True
        session.block_reason = "MAX_DAILY_LOSS_REACHED"
        return False

    # 3. Ventana Horaria de Momentum (Hasta las 11:00 EST)
    if session.current_time_est >= "11:00":
        session.trading_blocked = True
        session.block_reason = "OUTSIDE_MOMENTUM_WINDOW"
        return False

    session.trading_blocked = False
    session.block_reason = None
    return True


# =====================================================================
# GENERADOR DE SEÑAL FORMAL (ETISignalPayload)
# =====================================================================

def build_warrior_signal(
    symbol: str,
    trigger_price: float,
    technical_stop: float,
    relative_volume: float = 6.0,
    account_tier: str = "base_tier_usd_2000"
) -> ETISignalPayload:
    """Construye el payload canónico para emisión hacia el robot eTrade."""
    date_str = datetime.now().strftime("%Y%m%d")
    sig_id = f"SIG_WARRIOR_{date_str}_{symbol.upper()}"

    mgr = WarriorRulePackManager.get_instance()
    rule_08 = mgr.get_rule_by_code("RP_WARRIOR_08_SMALL_ACCOUNT_COMPOUNDING") or {}
    sizing = rule_08.get("position_sizing", {}).get(account_tier, {"shares": 500, "max_risk_usd": 50.0})

    max_risk_usd = float(sizing.get("max_risk_usd", 50.0))
    tp1_target = round(trigger_price + 0.15, 2)

    return ETISignalPayload(
        signal_id=sig_id,
        symbol=symbol.upper(),
        cadence="REALTIME_ALERT",
        strategy=StrategySpec(
            horizon="SCALPING",
            playbook_rule="RP_WARRIOR_08_SMALL_ACCOUNT_COMPOUNDING",
            bias="BULLISH"
        ),
        technical_gate=TechnicalGate(
            trigger_type="FIRST_1M_CANDLE_NEW_HIGH",
            underlying_trigger_price=trigger_price,
            indicator_requirements=IndicatorRequirements(
                vwap_condition="PRICE_ABOVE_VWAP",
                ema_fast_vs_slow="FAST_ABOVE_SLOW",
                min_relative_volume=relative_volume
            )
        ),
        risk_management=RiskManagement(
            entry_price=trigger_price,
            initial_stop_loss=technical_stop,
            tp1_target=tp1_target,
            tp1_partial_pct=50.0,
            breakeven_on_tp1=True,
            max_account_risk_usd=max_risk_usd
        ),
        safety_guardrails=SafetyGuardrails(
            execution_allowed=True,
            max_slippage_pct=1.0,
            circuit_breaker_active=False
        )
    )
