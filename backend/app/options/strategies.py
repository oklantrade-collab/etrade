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

STRATEGIES = ("long_call", "long_put", "bull_call_spread", "bear_put_spread")
SETTING_FLAG = {
    "long_call": "strat_long_call", "long_put": "strat_long_put",
    "bull_call_spread": "strat_bull_call_spread", "bear_put_spread": "strat_bear_put_spread",
}
STRATEGY_DIRECTION = {"long_call": "bullish", "bull_call_spread": "bullish",
                      "long_put": "bearish", "bear_put_spread": "bearish"}


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
    entry_debit: float             # por accion, ejecutable (ask - bid)
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
    value = sum((1 if leg["side"] == "buy" else -1) * intrinsic(leg["right"], leg["strike"], S) for leg in c.legs)
    return (value - c.entry_debit) * 100.0 - c.costs_contract


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
    if q.open_interest is None:
        out.append("dato no disponible: open_interest")
    elif q.open_interest < eff["min_contract_oi"]:
        out.append(f"OI {q.open_interest:.0f} < {eff['min_contract_oi']}")
    if q.volume is None:
        out.append("dato no disponible: volume")
    elif q.volume < eff["min_contract_volume"]:
        out.append(f"volumen {q.volume:.0f} < {eff['min_contract_volume']}")
    return out


def abs_delta(q: Q, S: float, today: date, eff: dict[str, Any]) -> tuple[float | None, str | None]:
    """|delta| del broker; si falta, delta BS a partir de la IV del broker; si tampoco hay IV -> None."""
    if q.delta is not None:
        return abs(q.delta), "broker"
    T = (q.expiry - today).days / 365.0
    r = float(eff["risk_free_rate_pct"]) / 100.0
    d = bs.bs_delta(S, q.strike, T, r, q.iv, q.right) if q.iv else None
    return (abs(d), "bs_from_iv") if d is not None else (None, None)


def _exit_plan(strategy: str, entry_debit: float, max_profit: float | None, eff: dict[str, Any]) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "force_close_min_before_close": eff["force_close_min_before_close"],
        "exit_on_direction_flip": eff["exit_on_direction_flip"],
        "exit_on_bad_data": True,
    }
    if strategy in ("long_call", "long_put"):
        plan["take_profit_premium"] = round(entry_debit * (1 + eff["long_tp_pct"] / 100), 4)
        plan["stop_premium"] = round(entry_debit * (1 - eff["long_sl_pct"] / 100), 4)
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
    qty = _qty(ml, eff)
    if qty < 1:
        return None, [f"perdida maxima ${ml:.2f}/contrato > riesgo por operacion ${eff['max_risk_per_trade_usd']}"]
    be = q.strike + ml / 100 if q.right == "C" else q.strike - ml / 100
    cand = Candidate(strategy, STRATEGY_DIRECTION[strategy], q.expiry, [_leg(q, "buy")], qty, debit,
                     round((q.bid + q.ask) / 2, 4), round(ml, 2), round(ml * qty, 2), None, round(be, 4),
                     round(costs, 2), None, _exit_plan(strategy, debit, None, eff), src)
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
    qty = _qty(ml, eff)
    if qty < 1:
        return None, [f"perdida maxima ${ml:.2f}/contrato > riesgo por operacion ${eff['max_risk_per_trade_usd']}"]
    be = long_q.strike + ml / 100 if long_q.right == "C" else long_q.strike - ml / 100
    cand = Candidate(strategy, STRATEGY_DIRECTION[strategy], long_q.expiry,
                     [_leg(long_q, "buy"), _leg(short_q, "sell")], qty, round(debit, 4), round(mid_debit, 4),
                     round(ml, 2), round(ml * qty, 2), round(max_profit, 2), round(be, 4), round(costs, 2),
                     round(overcost, 2), _exit_plan(strategy, debit, max_profit, eff), src)
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
        if not eff.get(SETTING_FLAG[strat]):
            continue
        if STRATEGY_DIRECTION[strat] not in directions:
            continue
        right = "C" if strat in ("long_call", "bull_call_spread") else "P"
        for exp, qs in by_exp.items():
            side = sorted([q for q in qs if q.right == right], key=lambda q: q.strike)
            for lq in side:
                if strat in ("long_call", "long_put"):
                    c, why = build_long(strat, lq, price, today, eff)
                    (valid.append(c) if c else rej(strat, [lq], why))
                else:
                    for sq in side:
                        if sq.strike == lq.strike:
                            continue
                        c, why = build_spread(strat, lq, sq, price, today, eff)
                        if c:
                            valid.append(c)
                        elif not (why and ("mal construido" in why[0])):
                            rej(strat, [lq, sq], why)
    return valid, rejected
