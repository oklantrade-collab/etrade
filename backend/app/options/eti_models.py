"""
eTrade — ETI (eTrade Intelligence) Signal & Tactical Models
============================================================
Implementación formal de los contratos de datos de integración entre ETI y eTrade
según la especificación C:\\Fuentes\\eTrade\\docs\\ETI_eTrade_Integration_Data_Contracts.md (v2.3.0).

Incluye el Instructivo Táctico de 5 Pilares de Radar Cuántico ETI:
1. Escenario Activo
2. Trigger de Activación (Nivel Subyacente)
3. Invalidación (Stop Técnico Forrester)
4. Rango Objetivo (Take Profit 1 & 2)
5. Racional Causal Forrester (Macro FDE / FCG Yoel Sardiñas / Carter / Sigma)
Y la gestión de doble gatillo:
- Prioridad 1: Microestructura Ross Cameron (Micro-Pullback 2m/5m + First Candle New High/Low)
- Opción 2: Trigger Directo ETI (Ruptura confirmada con volumen)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Literal, Dict, Any
from pydantic import BaseModel, Field


class OptionsContractSpec(BaseModel):
    contract_symbol: str
    option_type: Literal["CALL", "PUT"]
    strike: float
    expiration_date: str
    dte: int
    target_delta: float
    max_bid_ask_spread_pct: float = 4.0
    estimated_contract_price: float


class StrategySpec(BaseModel):
    horizon: Literal["SCALPING", "INTRADAY", "DAY_TRADE", "SWING"]
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL_RANGE"]
    playbook_rule: str
    expected_duration_minutes: int


class CausalContext(BaseModel):
    fde_regime: Literal["DECELERATION", "EXPANSION", "STAGFLATION", "RECOVERY"]
    fcg_confidence_pct: float
    primary_source: str
    catalyst_summary: str
    catalyst_impact_score: float
    greeks_thesis: str


class IndicatorRequirements(BaseModel):
    vwap_condition: Literal["PRICE_BELOW_VWAP", "PRICE_ABOVE_VWAP", "ANY"]
    ema_fast_vs_slow: Literal["FAST_BELOW_SLOW", "FAST_ABOVE_SLOW", "ANY"]
    min_relative_volume: float = 1.2
    timeframe_confirmation: Literal["1m", "2m", "5m"]


class TechnicalGate(BaseModel):
    trigger_type: Literal["VWAP_REJECTION", "PRICE_BREAKOUT", "ORB_BREAK", "EMA_PULLBACK"]
    underlying_trigger_price: float
    trigger_operator: Literal["LESS_THAN_OR_EQUAL", "GREATER_THAN_OR_EQUAL", "CROSS_BELOW", "CROSS_ABOVE"]
    indicator_requirements: IndicatorRequirements


class RiskManagement(BaseModel):
    invalidation_underlying: float
    stop_loss_contract_pct: float
    take_profit_1_pct: float
    take_profit_2_pct: float
    runner_trailing_stop_pct: float
    max_account_risk_pct: float = 2.5


class SafetyGuardrails(BaseModel):
    execution_allowed: bool = True
    max_slippage_pct: float = 1.5
    circuit_breaker_active: bool = False


class ETITacticalInstruction(BaseModel):
    """Instructivo Táctico de 5 Pilares de Radar Cuántico ETI."""
    escenario_activo: str
    trigger_activacion: float
    trigger_operator: str
    invalidacion_stop: float
    rango_objetivo: str
    racional_causal_forrester: str
    prioridad_1_ross_cameron: str = "Buscando Micro-Pullback 2m/5m hacia EMA9/VWAP"
    opcion_2_fallback_eti: str = "Esperando perforación directa con RVOL ≥ 1.2x"
    status_p1: Literal["WAITING_PULLBACK", "PULLBACK_FORMED", "TRIGGERED", "NOT_MET"] = "WAITING_PULLBACK"
    status_p2: Literal["MONITORING_PRICE", "TRIGGERED", "INVALIDATED"] = "MONITORING_PRICE"
    recommended_route: Literal["PRIORITY_1_ROSS_CAMERON", "OPTION_2_FALLBACK_ETI", "HYBRID_PENDING"] = "HYBRID_PENDING"


class ETISignal(BaseModel):
    """Estructura de señal unificada de Radar Cuántico ETI recibida por eTrade."""
    signal_id: str
    timestamp: str
    expires_at: str
    cadence: Literal["PRE_MARKET", "INTRADAY_5M", "INTRADAY_15M", "REALTIME_ALERT"]
    status: Literal["ACTIVE", "TRIGGERED", "TRIGGERED_AND_FILLED", "FILLED", "EXPIRED", "CANCELLED", "STANDBY"] = "ACTIVE"
    symbol: str
    asset_class: Literal["OPTION_0DTE", "OPTION_WEEKLY", "EQUITY", "FUTURE"]
    action: Literal["BUY_TO_OPEN", "SELL_TO_CLOSE", "STOP_LOSS", "TAKE_PROFIT"]
    options_contract: Optional[OptionsContractSpec] = None
    strategy: StrategySpec
    causal_context: CausalContext
    technical_gate: TechnicalGate
    risk_management: RiskManagement
    safety_guardrails: SafetyGuardrails
    tactical_instruction: Optional[ETITacticalInstruction] = None

    def get_or_create_tactical_instruction(self) -> ETITacticalInstruction:
        if self.tactical_instruction:
            return self.tactical_instruction

        trigger_op_sym = "≤" if self.technical_gate.trigger_operator in ("LESS_THAN_OR_EQUAL", "CROSS_BELOW") else "≥"
        is_put = (self.options_contract.option_type == "PUT") if self.options_contract else (self.strategy.bias == "BEARISH")
        
        target_str = (
            f"TP1: +{self.risk_management.take_profit_1_pct:.0f}% (50% lote) | "
            f"TP2: +{self.risk_management.take_profit_2_pct:.0f}% (30% lote) | "
            f"Runner: +{self.risk_management.runner_trailing_stop_pct:.0f}% Trailing"
        )
        
        racional_txt = (
            f"Régimen FDE {self.causal_context.fde_regime} ({self.causal_context.fcg_confidence_pct:.1f}% conf). "
            f"Fuente: {self.causal_context.primary_source}. {self.causal_context.catalyst_summary} "
            f"Griegas: {self.causal_context.greeks_thesis}"
        )

        p1_desc = (
            "First Candle New Low tras rebote a EMA9/VWAP en 2m/5m" if is_put
            else "First Candle New High tras retroceso a EMA9/VWAP en 2m/5m"
        )
        p2_desc = f"Ruptura directa de precio {trigger_op_sym} ${self.technical_gate.underlying_trigger_price:.2f} con RVOL ≥ {self.technical_gate.indicator_requirements.min_relative_volume:.1f}x"

        inst = ETITacticalInstruction(
            escenario_activo=self.strategy.playbook_rule,
            trigger_activacion=self.technical_gate.underlying_trigger_price,
            trigger_operator=self.technical_gate.trigger_operator,
            invalidacion_stop=self.risk_management.invalidation_underlying,
            rango_objetivo=target_str,
            racional_causal_forrester=racional_txt,
            prioridad_1_ross_cameron=p1_desc,
            opcion_2_fallback_eti=p2_desc,
            status_p1="WAITING_PULLBACK",
            status_p2="MONITORING_PRICE",
            recommended_route="HYBRID_PENDING"
        )
        self.tactical_instruction = inst
        return inst

    def to_opportunities_candidate(self, current_price: Optional[float] = None) -> Dict[str, Any]:
        """Convierte la señal en el formato de candidata de alta prioridad para /options/opportunities."""
        inst = self.get_or_create_tactical_instruction()
        is_call = self.options_contract.option_type == "CALL" if self.options_contract else (self.strategy.bias == "BULLISH")
        direction_str = "bullish" if is_call else "bearish"
        strat_type = "long_call" if is_call else "long_put"

        curr_px = current_price or (self.options_contract.strike if self.options_contract else 100.0)
        est_premium = self.options_contract.estimated_contract_price if self.options_contract else 2.50
        max_loss = est_premium * 100.0
        contract_symbol = self.options_contract.contract_symbol if self.options_contract else f"{self.symbol}0DTE"
        strike = self.options_contract.strike if self.options_contract else curr_px
        expiry = self.options_contract.expiration_date if self.options_contract else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dte = self.options_contract.dte if self.options_contract else 0

        legs = [{
            "side": "buy",
            "right": "C" if is_call else "P",
            "strike": strike,
            "expiry": expiry,
            "ratio": 1,
            "desc": f"+{'C' if is_call else 'P'}{strike:.1f} ({contract_symbol})",
            "open_interest": 500,
            "market_data_type": "LIVE"
        }]

        # Score institucional de máxima prioridad: 96.5 + bonificaciones por confianza causal
        conf_boost = (self.causal_context.fcg_confidence_pct - 80.0) * 0.15
        final_score = min(99.0, max(92.0, 96.0 + conf_boost))

        score_breakdown = {
            "score_total": final_score,
            "final_score": final_score,
            "setup_name": "ETI_QUANTUM_RADAR",
            "setup_label": f"⚡ RADAR CUÁNTICO ETI: {self.strategy.playbook_rule}",
            "is_eti_signal": True,
            "is_zero_dte": (dte == 0 or "0DTE" in self.asset_class),
            "eti_horizon": self.strategy.horizon,
            "fde_regime": self.causal_context.fde_regime,
            "fcg_confidence": self.causal_context.fcg_confidence_pct,
            "catalyst_name": self.causal_context.primary_source,
            "catalyst_summary": self.causal_context.catalyst_summary,
            "greeks_thesis": self.causal_context.greeks_thesis,
            "triggers_fired": ["TRIG_ETI_CAUSAL", "TRIG_ROSS_CAMERON_P1", "TRIG_ETI_TRIGGER_P2"],
            "p_touch_day_pct": min(95, int(self.causal_context.fcg_confidence_pct)),
            "expected_rr": round(self.risk_management.take_profit_1_pct / max(1.0, abs(self.risk_management.stop_loss_contract_pct)), 2),
            "invalidation_price": self.risk_management.invalidation_underlying,
            "trigger_price": self.technical_gate.underlying_trigger_price,
            "tactical_instruction": inst.model_dump(),
            "is_dead_stock": False,
            "eligible_by_score": True
        }

        exit_plan = {
            "is_eti_signal": True,
            "horizon": self.strategy.horizon,
            "take_profit_1_pct": self.risk_management.take_profit_1_pct,
            "take_profit_2_pct": self.risk_management.take_profit_2_pct,
            "stop_loss_pct": self.risk_management.stop_loss_contract_pct,
            "invalidation_underlying": self.risk_management.invalidation_underlying,
            "runner_trailing_stop_pct": self.risk_management.runner_trailing_stop_pct,
            "contract_symbol": contract_symbol,
            "estimated_entry_premium": est_premium
        }

        return {
            "id": f"eti-{self.signal_id}",
            "underlying_id": 9999001,
            "symbol": self.symbol,
            "action": self.action,
            "strategy_type": strat_type,
            "direction": direction_str,
            "direction_source": "eti_quantum_radar",
            "is_eti_signal": True,
            "is_gap_runner": False,
            "gap_type": None,
            "gap_pct": 0.0,
            "expiry": expiry,
            "dte": dte,
            "is_zero_dte": (dte == 0 or "0DTE" in self.asset_class),
            "legs": legs,
            "qty": 1,
            "entry_debit": est_premium,
            "mid_debit": est_premium,
            "max_loss_total": max_loss,
            "max_loss_contract": max_loss,
            "max_profit_contract": est_premium * 100.0 * (self.risk_management.take_profit_1_pct / 100.0),
            "breakeven": strike + est_premium if is_call else strike - est_premium,
            "ev_view_net": round(max_loss * 0.75, 2),
            "score": final_score,
            "eligibility_status": "selected",
            "rank_global": 1,
            "rank_strategy": 1,
            "created_at": self.timestamp,
            "expires_at": self.expires_at,
            "score_breakdown": score_breakdown,
            "exit_plan": exit_plan,
            "tactical_instruction": inst.model_dump(),
            "opt_underlyings": {
                "symbol": self.symbol,
                "price": curr_px,
                "apex_score": 95,
                "data_state": "LIVE",
                "direction": direction_str,
                "catalyst_meta": {
                    "primary_source": self.causal_context.primary_source,
                    "headline": self.causal_context.catalyst_summary,
                    "impact_score": self.causal_context.catalyst_impact_score
                }
            }
        }
