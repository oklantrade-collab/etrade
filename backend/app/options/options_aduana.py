"""ADUANA de Opciones (reglas O-1..O-11, doc §6.4). PROPIA del modulo: no modifica AduanaValidator.

Toda entrada y salida simulada debe pasar por aqui. Cada decision se devuelve con el detalle de cada regla
(para persistir en opt_aduana_decisions y System Logs).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.options import market_calendar as mc
from app.options import settings_defaults as sd
from app.options import health
from app.options import event_calendar

PASSIVE_EXITS = {
    "stop", "stop_loss", "forced_close_time", "bad_data_close",
    "sl_underlying_pierced", "ema_cross_15m", "ema3_flat_descending_1h", "ema3_flat_ascending_1h"
}
ACTIVE_EXITS = {
    "take_profit", "signal_invalidation", "manual_simulated",
    "tp_rsi_climax_1h", "tp_upper_6", "tp_lower_6", "sipv_trend_flip_1h", "ema3_flat_near_bb_upper_15m", "ema3_flat_near_bb_lower_15m"
}


def classify_exit(reason: str) -> str:
    """PASIVA / ACTIVA, alineado con el criterio ya usado en la plataforma."""
    if reason in PASSIVE_EXITS:
        return "PASIVA"
    if reason in ACTIVE_EXITS:
        return "ACTIVA"
    if "tp" in reason or "profit" in reason:
        return "ACTIVA"
    return "PASIVA"


@dataclass
class OpenPosition:
    underlying_id: int
    max_loss_total: float
    direction: str
    candidate_id: int | None = None


@dataclass
class AduanaContext:
    now: datetime
    positions: list[OpenPosition] = field(default_factory=list)
    realized_pnl_today: float = 0.0
    unrealized_pnl_today: float = 0.0       # marcada a liquidacion (bid/ask conservador)
    opened_candidate_ids: set[int] = field(default_factory=set)
    quote_ages_sec: dict[int, float] = field(default_factory=dict)   # conid -> antiguedad
    event_flags: list[str] | None = None    # None = no verificado
    underlying_id: int | None = None
    execution_mode: str = sd.EXECUTION_MODE
    check_quote_age: bool = True            # False al valorar candidatas (la antiguedad se exige al abrir)
    check_window: bool = True
    underlying: dict[str, Any] | None = None


@dataclass
class RuleResult:
    rule: str
    ok: bool
    detail: str


@dataclass
class AduanaResult:
    approved: bool
    rules: list[RuleResult]
    warnings: list[str] = field(default_factory=list)

    @property
    def reasons(self) -> list[str]:
        return [f"{r.rule}: {r.detail}" for r in self.rules if not r.ok]

    def to_dict(self) -> dict[str, Any]:
        return {"approved": self.approved, "rules": [r.__dict__ for r in self.rules], "warnings": self.warnings}


def open_risk(positions: list[OpenPosition]) -> float:
    return sum(p.max_loss_total for p in positions)


def remaining_open_risk(positions: list[OpenPosition], eff: dict[str, Any]) -> float:
    return max(float(eff["max_open_risk_usd"]) - open_risk(positions), 0.0)


def daily_stop_active(ctx: AduanaContext, eff: dict[str, Any]) -> bool:
    """Se activa por perdida realizada + marcada, NO por el riesgo teorico de posiciones abiertas (doc §12.2)."""
    return (ctx.realized_pnl_today + ctx.unrealized_pnl_today) <= -float(eff["daily_stop_usd"])


def validate_entry(cand: dict[str, Any], ctx: AduanaContext, eff: dict[str, Any]) -> AduanaResult:
    """Valida una candidata (fila de opt_candidates) contra O-1..O-11. Datos ausentes = regla no superada."""
    rules: list[RuleResult] = []
    warns: list[str] = []
    add = lambda rule, ok, detail: rules.append(RuleResult(rule, bool(ok), detail))  # noqa: E731
    legs = cand.get("legs") or []
    qty = cand.get("qty")
    max_loss_c = cand.get("max_loss_contract")

    # O-1 modo paper
    add("O-1", ctx.execution_mode == "paper" and sd.execution_mode_ok(), f"modo={ctx.execution_mode}")

    # O-2 riesgo definido: cada pierna vendida cubierta por una comprada (mismo tipo/vencimiento) y max_loss calculable
    sells = [l for l in legs if l.get("side") == "sell"]
    buys = [l for l in legs if l.get("side") == "buy"]
    covered = True
    for s in sells:
        covered &= any(b["right"] == s["right"] and b["expiry"] == s["expiry"] and
                       ((s["right"] == "C" and b["strike"] < s["strike"]) or (s["right"] == "P" and b["strike"] > s["strike"]))
                       for b in buys)
    add("O-2", bool(legs) and covered and max_loss_c is not None and max_loss_c > 0,
        "riesgo definido" if covered and max_loss_c else "pierna vendida sin cobertura o max_loss no calculable")

    # O-3 max_loss <= riesgo por operacion (techo duro incluido)
    cap = min(float(eff["max_risk_per_trade_usd"]), sd.hard_caps()["max_risk_per_trade_usd"])
    tot = cand.get("max_loss_total")
    add("O-3", tot is not None and qty and tot <= cap + 1e-9, f"max_loss_total={tot} cap={cap}")

    # O-4 riesgo abierto agregado
    rem = remaining_open_risk(ctx.positions, eff)
    rem = min(rem, max(sd.hard_caps()["max_open_risk_usd"] - open_risk(ctx.positions), 0.0))
    add("O-4", tot is not None and tot <= rem + 1e-9, f"max_loss_total={tot} riesgo_restante={rem:.2f}")

    # O-5 stop diario
    add("O-5", not daily_stop_active(ctx, eff),
        f"P&L del dia (realizado+marcado)={ctx.realized_pnl_today + ctx.unrealized_pnl_today:.2f} stop=-{eff['daily_stop_usd']}")

    # O-6 spread relativo por pierna y sobrecoste neto
    bad = []
    for l in legs:
        b, a = l.get("bid"), l.get("ask")
        if b is None or a is None or a <= 0:
            bad.append(f"{l.get('right')}{l.get('strike')}: sin bid/ask")
        elif (a - b) / a * 100 > eff["max_leg_spread_pct"] + 1e-9:
            bad.append(f"{l['right']}{l['strike']}: spread {(a - b) / a * 100:.1f}%")
    oc = cand.get("exec_overcost_pct")
    if len(legs) > 1 and (oc is None or oc > eff["max_exec_overcost_pct"] + 1e-9):
        bad.append(f"sobrecoste de ejecucion {oc}%")
    add("O-6", not bad, "; ".join(bad) or "spreads dentro de limites")

    # O-7 datos validos y recientes
    states = {l.get("market_data_type") for l in legs}
    ok_states = {"LIVE", "DELAYED"} if eff.get("allow_delayed_data") else {"LIVE"}
    data_ok = bool(states) and states <= ok_states
    if "DELAYED" in states:
        warns.append("datos retrasados (MODO PRUEBA)")
    stale = []
    if ctx.check_quote_age:
        for l in legs:
            age = ctx.quote_ages_sec.get(l.get("conid"))
            if age is None or age > float(eff["max_quote_age_sec"]):
                stale.append(f"conid {l.get('conid')}: antiguedad {age}")
    add("O-7", data_ok and not stale, f"estados={sorted(s for s in states if s)} {'; '.join(stale)}".strip())

    # O-8 ventana de entrada (con festivos y cierres tempranos)
    if ctx.check_window:
        okw, why = mc.entry_window(ctx.now, int(eff["entry_start_min_after_open"]), int(eff["entry_end_min_before_close"]))
        add("O-8", okw, why)
        if mc.FALLBACK_CALENDAR:
            warns.append("calendario de mercado de respaldo (sin festivos)")
    else:
        add("O-8", True, "no evaluada (valoracion de candidata)")

    # O-9 eventos binarios
    if ctx.event_flags is None:
        add("O-9", True, "no verificado (aviso)")
        warns.append("earnings/catalizador no verificado")
    else:
        blocked = bool(ctx.event_flags) and bool(eff["block_events_in_dte"])
        add("O-9", not blocked, f"eventos={ctx.event_flags}")

    # O-10 idempotencia
    cid = cand.get("id")
    add("O-10", cid is None or cid not in ctx.opened_candidate_ids, "candidata ya abierta" if cid in ctx.opened_candidate_ids else "ok")

    # O-11 una posicion por subyacente (+ limites de posiciones abiertas y misma direccion)
    uid = ctx.underlying_id or cand.get("underlying_id")
    dup = any(p.underlying_id == uid for p in ctx.positions)
    n_open = len(ctx.positions)
    same_dir = sum(1 for p in ctx.positions if p.direction == cand.get("direction"))
    problems = []
    if dup:
        problems.append("ya hay posicion en el subyacente")
    if n_open >= int(eff["max_open_positions"]):
        problems.append(f"posiciones abiertas {n_open} >= {eff['max_open_positions']}")
    if same_dir >= int(eff["max_same_direction"]):
        problems.append(f"posiciones en la misma direccion {same_dir} >= {eff['max_same_direction']}")
    add("O-11", not problems, "; ".join(problems) or "ok")

    # O-12 Gate subyacente: validacion de catalizadores (Gap&Go, SIPV mechas, EMA3 1h, anti-climax)
    gate_enabled = eff.get("gate_enabled", True)
    if not gate_enabled:
        add("O-12", True, "gate O-12 deshabilitado")
    else:
        cat_state = cand.get("catalyst_state")
        if not cat_state and ctx.underlying:
            cat_state = ctx.underlying.get("catalyst_state")
        
        if not cat_state:
            # Si la candidata no proviene de catalizador ni tiene estado de catalizador, pasa por compatibilidad
            add("O-12", True, "sin catalizador activo (aprobado por defecto)")
        else:
            bad_gate = []
            cand_dir = (cand.get("direction") or "").lower()
            is_bull = cand_dir in ("bullish", "call", "long")
            is_bear = cand_dir in ("bearish", "put", "short")

            # 1. Validacion de Gap si participo en la nominacion
            gap_info = cat_state.get("c1_gap") or {}
            gap_active = cat_state.get("c1_active", False) or gap_info.get("triggered", False)
            if gap_active:
                candles_checked = int(gap_info.get("candles_checked") or 2)
                if candles_checked < 2:
                    bad_gate.append("primer gap del dia: esperando apertura de la 2da vela de 5m para confirmar")
                
                gap_atr = abs(float(gap_info.get("gap_atr") or 0.0))
                min_gap = float(eff.get("gate_gap_min_atr") or 0.5)
                max_gap = float(eff.get("gate_gap_max_atr") or 3.0)
                if gap_atr < min_gap:
                    bad_gate.append(f"gap insuficiente ({gap_atr:.2f} ATR < {min_gap} ATR)")
                elif gap_atr > max_gap:
                    bad_gate.append(f"gap excesivo ({gap_atr:.2f} ATR > {max_gap} ATR: riesgo de agotamiento)")

            # 2. Pendiente EMA3 1H
            if is_bull and cat_state.get("is_ema3_1h_descending"):
                bad_gate.append("pendiente EMA3 1h contraria (descendente en CALL)")
            elif is_bear and cat_state.get("is_ema3_1h_ascending"):
                bad_gate.append("pendiente EMA3 1h contraria (ascendente en PUT)")

            # 3. Rechazo o absorcion SIPV contraria (mecha >= 40%)
            if is_bull and cat_state.get("sipv_upper_rejection"):
                bad_gate.append("anulado por mecha de rechazo SIPV superior (>= 40%)")
            elif is_bear and cat_state.get("sipv_lower_absorption"):
                bad_gate.append("anulado por mecha de absorcion SIPV inferior (>= 40%)")

            # 4. Anti-climax (no aplica en vela 1 de gap por definicion)
            if cat_state.get("is_anticlimax_blocked"):
                is_first_gap_candle = gap_active and int(gap_info.get("candles_checked") or 0) <= 1
                if not is_first_gap_candle:
                    bad_gate.append("bloqueo por condicion anti-climax detectada")

            add("O-12", not bad_gate, "; ".join(bad_gate) or "gate subyacente superado")

    # O-13 Multi-pata, estandares y sincronizacion (Addendum v1.1 §10, §7 & §6.4)
    bad_standards = []
    # 1. Multiplicador estandar 100
    allow_nonstandard = eff.get("allow_nonstandard_multiplier", False)
    if not allow_nonstandard:
        for l in legs:
            m = l.get("multiplier", 100)
            if m not in (100, None):
                bad_standards.append(f"multiplicador no estandar {m} != 100")
                break

    # 2. Ratio costes/riesgo
    c_costs = cand.get("costs_contract")
    c_ml = cand.get("max_loss_contract")
    if c_costs is not None and c_ml is not None and c_ml > 0:
        c2r = (float(c_costs) / float(c_ml)) * 100.0
        max_c2r = float(eff.get("max_cost_to_risk_ratio", 20.0))
        if c2r > max_c2r + 1e-6:
            bad_standards.append(f"ratio costes/riesgo {c2r:.1f}% > {max_c2r}%")

    # 3. Validacion creditos 0 < C < W
    strat_type = cand.get("strategy_type") or cand.get("strategy")
    if strat_type in ("bull_put_spread", "bear_call_spread"):
        debit = cand.get("entry_debit")
        if debit is not None:
            credit = -float(debit)
            if len(legs) >= 2:
                w = abs(float(legs[0].get("strike", 0.0)) - float(legs[1].get("strike", 0.0)))
                if credit <= 0:
                    bad_standards.append("credito neto <= 0")
                elif w > 0 and credit >= w:
                    bad_standards.append(f"credito {credit:.2f} >= ancho {w:.2f}")

    # 4. Sincronizacion temporal entre patas (skew)
    if len(legs) > 1:
        timestamps = []
        for l in legs:
            ts_val = l.get("timestamp") or l.get("updated_at")
            if ts_val:
                try:
                    if isinstance(ts_val, (int, float)):
                        timestamps.append(float(ts_val))
                    elif isinstance(ts_val, str):
                        timestamps.append(datetime.fromisoformat(ts_val.replace("Z", "+00:00")).timestamp())
                except Exception:
                    pass
        if len(timestamps) == len(legs) and len(timestamps) > 1:
            skew = max(timestamps) - min(timestamps)
            max_skew = float(eff.get("max_leg_quote_skew_sec", 3.0))
            if skew > max_skew:
                bad_standards.append(f"desincronizacion entre patas {skew:.1f}s > {max_skew}s")

    add("O-13", not bad_standards, "; ".join(bad_standards) or "estandares multi-pata y costes aprobados")

    # O-14 Cobertura minima del score y datos esenciales (§5.3 / B-14)
    cov = cand.get("coverage")
    min_cov = float(eff.get("min_coverage", 0.80))
    missing_essential = []
    missing_comps = cand.get("missing_components") or []
    for es in ("expectancy", "liquidity", "risk"):
        if es in missing_comps:
            missing_essential.append(es)
    
    cov_ok = (cov is None or cov >= min_cov - 1e-9) and not missing_essential
    cov_detail = f"cobertura={cov if cov is not None else 1.0:.2f} >= {min_cov}" if not missing_essential else f"faltan componentes esenciales: {missing_essential}"
    add("O-14", cov_ok, cov_detail)

    # O-15 Salud del sistema y Kill Switch (§4.2 / B-15)
    allowed, health_reason = health.can_open_new_position(eff)
    add("O-15", allowed, health_reason)

    # O-16 Revalidacion de precio al abrir y deriva maxima (§10.3 / B-17)
    drift = cand.get("price_drift_pct")
    max_drift = float(eff.get("max_price_drift_pct", 5.0))
    if drift is not None and drift > 0:
        add("O-16", drift <= max_drift + 1e-9, f"deriva={drift:.1f}% max={max_drift}%")
    else:
        add("O-16", True, "sin deriva de precio")

    return AduanaResult(approved=all(r.ok for r in rules), rules=rules, warnings=warns)


def validate_exit(reason: str, ctx: AduanaContext) -> AduanaResult:
    """Salidas simuladas: valida modo paper y clasifica PASIVA/ACTIVA."""
    kind = classify_exit(reason)
    ok = ctx.execution_mode == "paper" and sd.execution_mode_ok()
    return AduanaResult(ok, [RuleResult("O-1", ok, f"modo={ctx.execution_mode}"),
                             RuleResult("EXIT", True, f"{kind}: {reason}")])


def static_context(underlying_id: int | None = None, event_flags: list[str] | None = None,
                   underlying: dict[str, Any] | None = None) -> AduanaContext:
    """Contexto para valorar candidatas: sin posiciones, sin exigir ventana ni antiguedad (se exigen al abrir, Sprint 6)."""
    return AduanaContext(now=datetime.now(timezone.utc), underlying_id=underlying_id, event_flags=event_flags,
                         check_quote_age=False, check_window=False, underlying=underlying)


def rule_o14_coverage_and_critical_data(cand: dict[str, Any], eff: dict[str, Any]) -> tuple[bool, str, str]:
    """Regla O-14: Cobertura minima y componentes esenciales (Doc §5.3 / B-14)."""
    cov = cand.get("coverage")
    min_cov = float(eff.get("min_coverage", 0.80))
    missing_comps = cand.get("missing_components") or []
    missing_essential = [es for es in ("expectancy", "liquidity", "risk") if es in missing_comps]
    if missing_essential:
        return False, "MISSING_ESSENTIAL_COMPONENT", f"faltan componentes esenciales: {missing_essential}"
    if cov is not None and cov < min_cov - 1e-9:
        return False, "INSUFFICIENT_COVERAGE", f"cobertura={cov:.2f} < {min_cov:.2f}"
    return True, "PASS", "cobertura y componentes suficientes"


def rule_o15_system_health_and_kill_switch(cand: dict[str, Any], eff: dict[str, Any]) -> tuple[bool, str, str]:
    """Regla O-15: Salud del sistema y Kill Switch (Doc §4.2 / B-15)."""
    allowed, health_reason = health.can_open_new_position(eff)
    code = "PASS" if allowed else ("SYSTEM_HALTED" if "Kill switch" in health_reason or "HALTED" in health_reason else "SYSTEM_DEGRADED")
    return allowed, code, health_reason


def rule_o16_price_drift_revalidation(cand: dict[str, Any], current_underlying: float, current_debit: float, eff: dict[str, Any]) -> tuple[bool, str, str]:
    """Regla O-16: Revalidacion de deriva de precio al momento de abrir (Doc §10.3 / B-17)."""
    ref_s0 = float(cand.get("underlying_price") or current_underlying)
    ref_debit = float(cand.get("entry_debit") or current_debit)
    max_drift = float(eff.get("max_price_drift_pct", 3.0))
    drift_s = abs(current_underlying - ref_s0) / ref_s0 * 100.0 if ref_s0 > 0 else 0.0
    drift_d = abs(current_debit - ref_debit) / ref_debit * 100.0 if ref_debit > 0 else 0.0
    drift = max(drift_s, drift_d)
    if drift > max_drift:
        return False, "PRICE_DRIFT_EXCEEDED", f"deriva {drift:.1f}% > {max_drift:.1f}%"
    return True, "PASS", f"deriva {drift:.1f}% <= {max_drift:.1f}%"

