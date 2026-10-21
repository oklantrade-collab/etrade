"""Estrategias V1 (doc §9.1): Long Call, Long Put, Bull Call Spread, Bear Put Spread. Logica pura.

Convenciones:
- Precios por accion; 1 contrato = 100 acciones. USD por contrato salvo indicacion.
- Ejecucion conservadora: compras al ask, ventas al bid (+ slippage y comisiones).
- Dato ausente = rechazo con motivo (nunca se rellena con cero).
- max_loss incluye costes (comisiones/fees ida y vuelta + slippage de entrada por pierna).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.options import bs
from app.options.strategies_catalog import STRATEGY_CATALOG

STRATEGIES = (
    "long_call",
    "long_put",
    "bull_call_spread",
    "bear_put_spread",
    "bull_put_spread",
    "bear_call_spread",
)
SETTING_FLAG = {
    "long_call": "strat_long_call",
    "long_put": "strat_long_put",
    "bull_call_spread": "strat_bull_call_spread",
    "bear_put_spread": "strat_bear_put_spread",
    "bull_put_spread": "strat_bull_put_spread",
    "bear_call_spread": "strat_bear_call_spread",
    "long_straddle": "strat_long_straddle",
    "long_strangle": "strat_long_strangle",
    "iron_condor": "strat_iron_condor",
    "iron_butterfly": "strat_iron_butterfly",
    "long_call_butterfly": "strat_long_call_butterfly",
    "long_put_butterfly": "strat_long_put_butterfly",
    "calendar_spread": "strat_calendar_spread",
    "diagonal_spread": "strat_diagonal_spread",
}
STRATEGY_DIRECTION = {
    "long_call": "bullish",
    "bull_call_spread": "bullish",
    "bull_put_spread": "bullish",
    "long_put": "bearish",
    "bear_put_spread": "bearish",
    "bear_call_spread": "bearish",
    "long_straddle": "volatile",
    "long_strangle": "volatile",
    "iron_condor": "neutral",
    "iron_butterfly": "neutral",
    "long_call_butterfly": "neutral",
    "long_put_butterfly": "neutral",
    "calendar_spread": "neutral",
    "diagonal_spread": "bullish",
}


@dataclass
class Q:
    """Contrato + ultima cotizacion (lo que carga candidates.py desde Supabase)."""
    contract_id: int
    conid: int
    right: str            # 'C' | 'P'
    strike: float
    expiry: date
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    open_interest: float | None = None
    iv: float | None = None
    delta: float | None = None
    usable: bool = False
    unusable_reason: str | None = None
    market_data_type: str | None = None
    multiplier: int = 100


@dataclass
class Candidate:
    strategy: str
    direction: str
    expiry: date
    legs: list[dict[str, Any]]
    qty: int
    entry_debit: float             # por accion, ejecutable (ask - bid) o negativo si credito
    mid_debit: float               # por accion, a mid (referencia)
    max_loss_contract: float       # USD por contrato, con costes
    max_loss_total: float          # qty * max_loss_contract
    max_profit_contract: float | None   # None = ilimitado teorico
    breakeven: float
    costs_contract: float
    exec_overcost_pct: float | None
    exit_plan: dict[str, Any] = field(default_factory=dict)
    delta_source: str | None = None
    warnings: list[str] = field(default_factory=list)
    family: str = "vertical"
    credit_or_debit: str = "debit"


# ------------------------------------------------------------------ costes y payoff
def contract_costs(n_legs: int, eff: dict[str, Any]) -> float:
    """USD por contrato: comision+fees ida y vuelta por pierna + slippage de entrada por pierna."""
    per_leg_round_trip = 2.0 * (float(eff["commission_per_contract"]) + float(eff["extra_fees_per_contract"]))
    slip = float(eff["slippage_normal"]) * 100.0
    return n_legs * (per_leg_round_trip + slip)


def intrinsic(right: str, strike: float, S: float) -> float:
    return max(0.0, S - strike) if right == "C" else max(0.0, strike - S)


def pnl_at_expiry(c: Candidate, S: float) -> float:
    """P&L neto por contrato al vencimiento (con costes) si el subyacente termina en S, qty=1."""
    pnl = 0.0
    for leg in c.legs:
        side = 1.0 if leg["side"] == "buy" else -1.0
        intr = intrinsic(leg["right"], leg["strike"], S)
        px = float(leg.get("exec_price") or 0.0)
        pnl += side * (intr - px) * 100.0
    return pnl - c.costs_contract


# ------------------------------------------------------------------ chequeos de calidad
def leg_issues(q: Q, eff: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if not q.usable:
        return [f"cotizacion no utilizable ({q.unusable_reason or q.market_data_type or 'sin estado'})"]
    if q.bid is None or q.ask is None or q.bid <= 0 or q.ask <= 0 or q.ask < q.bid:
        return ["bid/ask invalido"]
    sp = (q.ask - q.bid) / q.ask * 100
    if sp > eff["max_leg_spread_pct"] + 1e-9:   # tolerancia: 0.02/0.20 == 10.000000000000002
        out.append(f"spread de pierna {sp:.1f}% > {eff['max_leg_spread_pct']}%")
    allow_delayed = bool(eff.get("allow_delayed_data"))
    min_oi = eff.get("min_contract_oi", 0)
    if min_oi > 0:
        if q.open_interest is None:
            if not allow_delayed:
                out.append("dato no disponible: open_interest")
        elif q.open_interest < min_oi:
            out.append(f"OI {q.open_interest:.0f} < {min_oi}")

    min_vol = eff.get("min_contract_volume", 0)
    if min_vol > 0:
        if q.volume is None:
            if not allow_delayed:
                out.append("dato no disponible: volume")
        elif q.volume < min_vol:
            out.append(f"volumen {q.volume:.0f} < {min_vol}")
    return out


def abs_delta(q: Q, S: float, today: date, eff: dict[str, Any]) -> tuple[float | None, str | None]:
    """|delta| del broker; si falta, delta BS a partir de la IV del broker; si tampoco hay IV -> None."""
    if q.delta is not None:
        return abs(q.delta), "broker"
    T = (q.expiry - today).days / 365.0
    r = float(eff["risk_free_rate_pct"]) / 100.0
    d = bs.bs_delta(S, q.strike, T, r, q.iv, q.right) if q.iv else None
    return (abs(d), "bs_from_iv") if d is not None else (None, None)


def _exit_plan(strategy: str, entry_debit: float, max_profit: float | None, eff: dict[str, Any],
               max_loss: float | None = None) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "force_close_min_before_close": eff["force_close_min_before_close"],
        "exit_on_direction_flip": eff["exit_on_direction_flip"],
        "exit_on_bad_data": True,
    }
    if strategy in ("long_call", "long_put"):
        plan["take_profit_premium"] = round(entry_debit * (1 + eff["long_tp_pct"] / 100), 4)
        plan["stop_premium"] = round(entry_debit * (1 - eff["long_sl_pct"] / 100), 4)
    elif strategy in ("bull_put_spread", "bear_call_spread"):
        plan["take_profit_pnl_contract"] = round((max_profit or 0) * eff["spread_tp_pct"] / 100, 2)
        loss_base = max_loss if max_loss is not None else abs(entry_debit * 100)
        plan["stop_pnl_contract"] = round(-loss_base * eff["spread_sl_pct"] / 100, 2)
        plan["short_leg_delta_exit"] = float(eff.get("short_leg_delta_exit", 0.70))
    else:
        plan["take_profit_pnl_contract"] = round((max_profit or 0) * eff["spread_tp_pct"] / 100, 2)
        plan["stop_pnl_contract"] = round(-entry_debit * 100 * eff["spread_sl_pct"] / 100, 2)
    return plan


def _qty(max_loss_contract: float, eff: dict[str, Any]) -> int:
    return int(math.floor(float(eff["max_risk_per_trade_usd"]) / max_loss_contract)) if max_loss_contract > 0 else 0


def _leg(q: Q, side: str) -> dict[str, Any]:
    px = q.ask if side == "buy" else q.bid
    return {"conid": q.conid, "contract_id": q.contract_id, "right": q.right, "strike": q.strike,
            "expiry": q.expiry.isoformat(), "side": side, "exec_price": px, "bid": q.bid, "ask": q.ask,
            "mid": round((q.bid + q.ask) / 2, 4), "iv": q.iv, "delta": q.delta, "market_data_type": q.market_data_type}


# ------------------------------------------------------------------ constructores
def build_long(strategy: str, q: Q, S: float, today: date, eff: dict[str, Any]) -> tuple[Candidate | None, list[str]]:
    reasons = leg_issues(q, eff)
    d, src = abs_delta(q, S, today, eff)
    if d is None:
        reasons.append("dato no disponible: delta (ni IV para estimarla)")
    elif not (eff["delta_min"] <= d <= eff["delta_max"]):
        reasons.append(f"|delta| {d:.2f} fuera de [{eff['delta_min']}, {eff['delta_max']}]")
    if reasons:
        return None, reasons
    debit = q.ask
    costs = contract_costs(1, eff)
    ml = debit * 100 + costs

    # Filtro ratio costes/riesgo (§6.4)
    c2r = (costs / ml) * 100.0 if ml > 0 else 100.0
    max_c2r = float(eff.get("max_cost_to_risk_ratio", 20.0))
    if c2r > max_c2r:
        return None, [f"ratio costes/riesgo {c2r:.1f}% > {max_c2r}%"]

    qty = _qty(ml, eff)
    if qty < 1:
        return None, [f"perdida maxima ${ml:.2f}/contrato > riesgo por operacion ${eff['max_risk_per_trade_usd']}"]
    be = q.strike + ml / 100 if q.right == "C" else q.strike - ml / 100
    cand = Candidate(
        strategy=strategy,
        direction=STRATEGY_DIRECTION[strategy],
        expiry=q.expiry,
        legs=[_leg(q, "buy")],
        qty=qty,
        entry_debit=debit,
        mid_debit=round((q.bid + q.ask) / 2, 4),
        max_loss_contract=round(ml, 2),
        max_loss_total=round(ml * qty, 2),
        max_profit_contract=None,
        breakeven=round(be, 4),
        costs_contract=round(costs, 2),
        exec_overcost_pct=None,
        exit_plan=_exit_plan(strategy, debit, None, eff),
        delta_source=src,
        family="single-leg",
        credit_or_debit="debit",
    )
    if src == "bs_from_iv":
        cand.warnings.append("delta estimada con Black-Scholes desde IV del broker")
    return cand, []


def build_spread(strategy: str, long_q: Q, short_q: Q, S: float, today: date,
                 eff: dict[str, Any]) -> tuple[Candidate | None, list[str]]:
    reasons: list[str] = []
    if long_q.expiry != short_q.expiry or long_q.right != short_q.right:
        return None, ["piernas con distinto vencimiento o tipo"]
    width = abs(short_q.strike - long_q.strike)
    if strategy == "bull_call_spread" and not short_q.strike > long_q.strike:
        return None, ["bull call spread mal construido (K corto debe ser > K largo)"]
    if strategy == "bear_put_spread" and not short_q.strike < long_q.strike:
        return None, ["bear put spread mal construido (K corto debe ser < K largo)"]
    if width < eff["spread_width_min"] or width > eff["spread_width_max"]:
        return None, [f"ancho {width:g} fuera de [{eff['spread_width_min']}, {eff['spread_width_max']}]"]
    reasons += [f"pierna larga: {r}" for r in leg_issues(long_q, eff)]
    reasons += [f"pierna corta: {r}" for r in leg_issues(short_q, eff)]
    d, src = abs_delta(long_q, S, today, eff)
    if d is None:
        reasons.append("dato no disponible: delta pierna larga (ni IV para estimarla)")
    elif not (eff["delta_min"] <= d <= eff["delta_max"]):
        reasons.append(f"|delta| pierna larga {d:.2f} fuera de [{eff['delta_min']}, {eff['delta_max']}]")
    if reasons:
        return None, reasons

    debit = long_q.ask - short_q.bid
    mid_debit = (long_q.bid + long_q.ask) / 2 - (short_q.bid + short_q.ask) / 2
    if debit <= 0:
        return None, ["debito ejecutable <= 0 (cotizaciones inconsistentes)"]
    if debit >= width:
        return None, [f"debito {debit:.2f} >= ancho {width:g}: sin beneficio posible"]
    costs = contract_costs(2, eff)
    ml = debit * 100 + costs
    max_profit = (width - debit) * 100 - costs
    if max_profit <= 0:
        return None, ["sin beneficio posible tras costes"]
    overcost = ((debit - mid_debit) / mid_debit * 100) if mid_debit > 0 else None
    if overcost is None:
        return None, ["debito a mid <= 0: sobrecoste de ejecucion no calculable"]
    if overcost > eff["max_exec_overcost_pct"]:
        return None, [f"sobrecoste de ejecucion {overcost:.1f}% > {eff['max_exec_overcost_pct']}%"]

    # Filtro ratio costes/riesgo (§6.4)
    c2r = (costs / ml) * 100.0 if ml > 0 else 100.0
    max_c2r = float(eff.get("max_cost_to_risk_ratio", 20.0))
    if c2r > max_c2r:
        return None, [f"ratio costes/riesgo {c2r:.1f}% > {max_c2r}%"]

    qty = _qty(ml, eff)
    if qty < 1:
        return None, [f"perdida maxima ${ml:.2f}/contrato > riesgo por operacion ${eff['max_risk_per_trade_usd']}"]
    be = long_q.strike + ml / 100 if long_q.right == "C" else long_q.strike - ml / 100
    cand = Candidate(
        strategy=strategy,
        direction=STRATEGY_DIRECTION[strategy],
        expiry=long_q.expiry,
        legs=[_leg(long_q, "buy"), _leg(short_q, "sell")],
        qty=qty,
        entry_debit=round(debit, 4),
        mid_debit=round(mid_debit, 4),
        max_loss_contract=round(ml, 2),
        max_loss_total=round(ml * qty, 2),
        max_profit_contract=round(max_profit, 2),
        breakeven=round(be, 4),
        costs_contract=round(costs, 2),
        exec_overcost_pct=round(overcost, 2),
        exit_plan=_exit_plan(strategy, debit, max_profit, eff),
        delta_source=src,
        family="vertical",
        credit_or_debit="debit",
    )
    if src == "bs_from_iv":
        cand.warnings.append("delta estimada con Black-Scholes desde IV del broker")
    return cand, []


def build_vertical_credit(strategy: str, short_q: Q, long_q: Q, S: float, today: date,
                         eff: dict[str, Any]) -> tuple[Candidate | None, list[str]]:
    """Construye un spread vertical de credito (Bull Put o Bear Call).
    - Bull Put Spread: Vende Put K_alto (short_q), compra Put K_bajo (long_q).
    - Bear Call Spread: Vende Call K_bajo (short_q), compra Call K_alto (long_q).
    """
    reasons: list[str] = []
    if short_q.expiry != long_q.expiry or short_q.right != long_q.right:
        return None, ["piernas con distinto vencimiento o tipo"]

    width = abs(short_q.strike - long_q.strike)
    if strategy == "bull_put_spread":
        if short_q.right != "P":
            return None, ["bull put spread debe ser con PUTs"]
        if not (short_q.strike > long_q.strike):
            return None, ["bull put spread mal construido (K corto debe ser > K largo)"]
    elif strategy == "bear_call_spread":
        if short_q.right != "C":
            return None, ["bear call spread debe ser con CALLs"]
        if not (short_q.strike < long_q.strike):
            return None, ["bear call spread mal construido (K corto debe ser < K largo)"]
    else:
        return None, [f"estrategia de credito no soportada: {strategy}"]

    if width < eff["spread_width_min"] or width > eff["spread_width_max"]:
        return None, [f"ancho {width:g} fuera de [{eff['spread_width_min']}, {eff['spread_width_max']}]"]

    reasons += [f"pierna corta: {r}" for r in leg_issues(short_q, eff)]
    reasons += [f"pierna larga: {r}" for r in leg_issues(long_q, eff)]

    d, src = abs_delta(short_q, S, today, eff)
    if d is None:
        reasons.append("dato no disponible: delta pierna corta (ni IV para estimarla)")
    elif not (eff["delta_min"] <= d <= eff["delta_max"]):
        reasons.append(f"|delta| pierna corta {d:.2f} fuera de [{eff['delta_min']}, {eff['delta_max']}]")

    if reasons:
        return None, reasons

    # Credito ejecutable: vende pierna corta al bid, compra pierna larga al ask
    credit = short_q.bid - long_q.ask
    mid_credit = (short_q.bid + short_q.ask) / 2.0 - (long_q.bid + long_q.ask) / 2.0

    if credit <= 0:
        return None, ["credito ejecutable <= 0 (cotizaciones inconsistentes o credito nulo)"]
    if credit >= width:
        return None, [f"credito {credit:.2f} >= ancho {width:g}: estructura invalida o arbitraje aparente"]

    costs = contract_costs(2, eff)
    ml = (width - credit) * 100.0 + costs
    max_profit = credit * 100.0 - costs
    if max_profit <= 0:
        return None, ["sin beneficio posible tras costes"]

    # Sobrecoste de ejecucion en credito: (mid_credit - credit) / mid_credit * 100
    overcost = ((mid_credit - credit) / mid_credit * 100.0) if mid_credit > 0 else None
    if overcost is None:
        return None, ["credito a mid <= 0: sobrecoste de ejecucion no calculable"]
    max_oc = float(eff.get("max_credit_overcost_pct", 15.0))
    if overcost > max_oc:
        return None, [f"sobrecoste de ejecucion en credito {overcost:.1f}% > {max_oc}%"]

    # Ratio costes/riesgo (§6.4)
    c2r = (costs / ml) * 100.0 if ml > 0 else 100.0
    max_c2r = float(eff.get("max_cost_to_risk_ratio", 20.0))
    if c2r > max_c2r:
        return None, [f"ratio costes/riesgo {c2r:.1f}% > {max_c2r}%"]

    qty = _qty(ml, eff)
    if qty < 1:
        return None, [f"perdida maxima ${ml:.2f}/contrato > riesgo por operacion ${eff['max_risk_per_trade_usd']}"]

    # Break-even
    # Bull Put: K_short - credit + costs/100
    # Bear Call: K_short + credit - costs/100
    if strategy == "bull_put_spread":
        be = short_q.strike - credit + (costs / 100.0)
    else:
        be = short_q.strike + credit - (costs / 100.0)

    # entry_debit negativo indica entrada en credito
    entry_debit = -round(credit, 4)
    mid_debit = -round(mid_credit, 4)

    exit_plan = _exit_plan(strategy, entry_debit, max_profit, eff, max_loss=ml)

    cand = Candidate(
        strategy=strategy,
        direction=STRATEGY_DIRECTION[strategy],
        expiry=short_q.expiry,
        legs=[_leg(short_q, "sell"), _leg(long_q, "buy")],
        qty=qty,
        entry_debit=entry_debit,
        mid_debit=mid_debit,
        max_loss_contract=round(ml, 2),
        max_loss_total=round(ml * qty, 2),
        max_profit_contract=round(max_profit, 2),
        breakeven=round(be, 4),
        costs_contract=round(costs, 2),
        exec_overcost_pct=round(overcost, 2),
        exit_plan=exit_plan,
        delta_source=src,
        family="vertical",
        credit_or_debit="credit",
    )
    if src == "bs_from_iv":
        cand.warnings.append("delta estimada con Black-Scholes desde IV del broker")
    return cand, []


# ------------------------------------------------------------------ generador
def generate(quotes: list[Q], price: float, today: date, eff: dict[str, Any],
             directions: tuple[str, ...] = ("bullish", "bearish")) -> tuple[list[Candidate], list[dict[str, Any]]]:
    """Genera candidatas y descartes (con motivo) para un subyacente. Sin forzar resultados."""
    valid: list[Candidate] = []
    rejected: list[dict[str, Any]] = []

    def rej(strategy: str, qs: list[Q], reasons: list[str]) -> None:
        rejected.append({"strategy": strategy, "expiry": qs[0].expiry.isoformat(),
                         "legs": [f"{q.right}{q.strike:g}@{q.expiry}" for q in qs], "reasons": reasons})

    by_exp: dict[date, list[Q]] = {}
    for q in quotes:
        by_exp.setdefault(q.expiry, []).append(q)

    for strat in STRATEGIES:
        flag = SETTING_FLAG.get(strat)
        if not flag or not eff.get(flag):
            continue
        if STRATEGY_DIRECTION[strat] not in directions:
            continue

        if strat in ("long_call", "long_put"):
            right = "C" if strat == "long_call" else "P"
            for exp, qs in by_exp.items():
                side = sorted([q for q in qs if q.right == right], key=lambda q: q.strike)
                for lq in side:
                    c, why = build_long(strat, lq, price, today, eff)
                    (valid.append(c) if c else rej(strat, [lq], why))

        elif strat in ("bull_call_spread", "bear_put_spread"):
            right = "C" if strat == "bull_call_spread" else "P"
            for exp, qs in by_exp.items():
                side = sorted([q for q in qs if q.right == right], key=lambda q: q.strike)
                for lq in side:
                    for sq in side:
                        if sq.strike == lq.strike:
                            continue
                        c, why = build_spread(strat, lq, sq, price, today, eff)
                        if c:
                            valid.append(c)
                        elif not (why and ("mal construido" in why[0])):
                            rej(strat, [lq, sq], why)

        elif strat in ("bull_put_spread", "bear_call_spread"):
            right = "P" if strat == "bull_put_spread" else "C"
            for exp, qs in by_exp.items():
                side = sorted([q for q in qs if q.right == right], key=lambda q: q.strike)
                for sq in side:
                    for lq in side:
                        if sq.strike == lq.strike:
                            continue
                        c, why = build_vertical_credit(strat, sq, lq, price, today, eff)
                        if c:
                            valid.append(c)
                        elif not (why and ("mal construido" in why[0])):
                            rej(strat, [sq, lq], why)

    return valid, rejected
