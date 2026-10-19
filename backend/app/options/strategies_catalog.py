"""Catalogo Maestro de Estrategias de Opciones (Addendum v1.1).
Define las 14 estrategias, familias UI, viabilidad economica segun capital ($50 max loss),
motor generico de payoff por suma de patas (§4.1) y oraculo de formulas cerradas (§4.2).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class StrategyDefinition:
    key: str
    name: str
    family: str            # 'single-leg' | 'vertical' | 'multi-leg defined-risk' | 'calendar/diagonal'
    direction: str         # 'bullish' | 'bearish' | 'neutral' | 'volatile'
    legs_count: int
    credit_or_debit: str   # 'debit' | 'credit'
    natural_horizon: str   # 'intraday' | 'multi-day'
    initial_state: str     # 'enabled' | 'shadow' | 'experimental' | 'disabled'
    capital_viable: bool   # Viable con $50 de riesgo por operacion y costes reales
    viability_note: str


STRATEGY_CATALOG: dict[str, StrategyDefinition] = {
    # 1. Long Call
    "long_call": StrategyDefinition(
        key="long_call",
        name="Long Call",
        family="single-leg",
        direction="bullish",
        legs_count=1,
        credit_or_debit="debit",
        natural_horizon="intraday",
        initial_state="enabled",
        capital_viable=True,
        viability_note="1 contrato, costes ~$3.40 (6.8% del riesgo de $50). Viable con prima <= $0.47.",
    ),
    # 2. Long Put
    "long_put": StrategyDefinition(
        key="long_put",
        name="Long Put",
        family="single-leg",
        direction="bearish",
        legs_count=1,
        credit_or_debit="debit",
        natural_horizon="intraday",
        initial_state="enabled",
        capital_viable=True,
        viability_note="1 contrato, costes ~$3.40 (6.8% del riesgo de $50). Viable con prima <= $0.47.",
    ),
    # 3. Bull Call Spread
    "bull_call_spread": StrategyDefinition(
        key="bull_call_spread",
        name="Bull Call Spread",
        family="vertical",
        direction="bullish",
        legs_count=2,
        credit_or_debit="debit",
        natural_horizon="intraday",
        initial_state="enabled",
        capital_viable=True,
        viability_note="2 contratos, costes ~$6.80 (13.6% de $50). Viable con debito neto <= $0.43.",
    ),
    # 4. Bear Put Spread
    "bear_put_spread": StrategyDefinition(
        key="bear_put_spread",
        name="Bear Put Spread",
        family="vertical",
        direction="bearish",
        legs_count=2,
        credit_or_debit="debit",
        natural_horizon="intraday",
        initial_state="enabled",
        capital_viable=True,
        viability_note="2 contratos, costes ~$6.80 (13.6% de $50). Viable con debito neto <= $0.43.",
    ),
    # 5. Bull Put Spread (Vertical Credito)
    "bull_put_spread": StrategyDefinition(
        key="bull_put_spread",
        name="Bull Put Spread",
        family="vertical",
        direction="bullish",
        legs_count=2,
        credit_or_debit="credit",
        natural_horizon="intraday",
        initial_state="enabled",
        capital_viable=True,
        viability_note="2 contratos, costes ~$6.80 (13.6% de $50). Viable si (W - C) <= $0.43 con ancho estrecho (W=1.0).",
    ),
    # 6. Bear Call Spread (Vertical Credito)
    "bear_call_spread": StrategyDefinition(
        key="bear_call_spread",
        name="Bear Call Spread",
        family="vertical",
        direction="bearish",
        legs_count=2,
        credit_or_debit="credit",
        natural_horizon="intraday",
        initial_state="enabled",
        capital_viable=True,
        viability_note="2 contratos, costes ~$6.80 (13.6% de $50). Viable si (W - C) <= $0.43 con ancho estrecho (W=1.0).",
    ),
    # 7. Long Straddle
    "long_straddle": StrategyDefinition(
        key="long_straddle",
        name="Long Straddle",
        family="multi-leg defined-risk",
        direction="volatile",
        legs_count=2,
        credit_or_debit="debit",
        natural_horizon="intraday",
        initial_state="disabled",
        capital_viable=False,
        viability_note="Marginal con $50: primas totales (Call+Put) casi siempre superan $0.43 salvo micro-caps.",
    ),
    # 8. Long Strangle
    "long_strangle": StrategyDefinition(
        key="long_strangle",
        name="Long Strangle",
        family="multi-leg defined-risk",
        direction="volatile",
        legs_count=2,
        credit_or_debit="debit",
        natural_horizon="intraday",
        initial_state="disabled",
        capital_viable=False,
        viability_note="Marginal con $50: primas totales deben ser <= $0.43; obliga a strikes muy OTM de baja probabilidad.",
    ),
    # 9. Iron Condor
    "iron_condor": StrategyDefinition(
        key="iron_condor",
        name="Iron Condor",
        family="multi-leg defined-risk",
        direction="neutral",
        legs_count=4,
        credit_or_debit="credit",
        natural_horizon="multi-day",
        initial_state="disabled",
        capital_viable=False,
        viability_note="Inviable con $50: 4 contratos -> costes $13.60 (27.2% del riesgo > 20% max). Horizonte natural multi-dia.",
    ),
    # 10. Iron Butterfly
    "iron_butterfly": StrategyDefinition(
        key="iron_butterfly",
        name="Iron Butterfly",
        family="multi-leg defined-risk",
        direction="neutral",
        legs_count=4,
        credit_or_debit="credit",
        natural_horizon="multi-day",
        initial_state="disabled",
        capital_viable=False,
        viability_note="Inviable con $50: 4 contratos -> costes 27.2% > 20%. Horizonte natural multi-dia.",
    ),
    # 11. Long Call Butterfly
    "long_call_butterfly": StrategyDefinition(
        key="long_call_butterfly",
        name="Long Call Butterfly",
        family="multi-leg defined-risk",
        direction="neutral",
        legs_count=4,
        credit_or_debit="debit",
        natural_horizon="multi-day",
        initial_state="experimental",
        capital_viable=False,
        viability_note="Experimental: requiere modelo de precio objetivo validado y horizonte multi-dia.",
    ),
    # 12. Long Put Butterfly
    "long_put_butterfly": StrategyDefinition(
        key="long_put_butterfly",
        name="Long Put Butterfly",
        family="multi-leg defined-risk",
        direction="neutral",
        legs_count=4,
        credit_or_debit="debit",
        natural_horizon="multi-day",
        initial_state="experimental",
        capital_viable=False,
        viability_note="Experimental: requiere modelo de precio objetivo validado y horizonte multi-dia.",
    ),
    # 13. Calendar Spread
    "calendar_spread": StrategyDefinition(
        key="calendar_spread",
        name="Calendar Spread",
        family="calendar/diagonal",
        direction="neutral",
        legs_count=2,
        credit_or_debit="debit",
        natural_horizon="multi-day",
        initial_state="experimental",
        capital_viable=False,
        viability_note="Experimental (solo analisis): requiere repricing multi-vencimiento con curva de IV.",
    ),
    # 14. Diagonal Spread
    "diagonal_spread": StrategyDefinition(
        key="diagonal_spread",
        name="Diagonal Spread",
        family="calendar/diagonal",
        direction="bullish",
        legs_count=2,
        credit_or_debit="debit",
        natural_horizon="multi-day",
        initial_state="experimental",
        capital_viable=False,
        viability_note="Experimental (solo analisis): requiere repricing multi-vencimiento con curva de IV.",
    ),
}


def get_all_strategies() -> list[dict[str, Any]]:
    return [d.__dict__ for d in STRATEGY_CATALOG.values()]


def get_strategy_definition(key: str) -> Optional[StrategyDefinition]:
    return STRATEGY_CATALOG.get(key)


def get_viable_strategies_for_capital(max_risk_usd: float = 50.0) -> list[str]:
    """Retorna las claves de estrategias que son matematicamente operables con el capital dado."""
    return [k for k, v in STRATEGY_CATALOG.items() if v.capital_viable]


# ---------------------------------------------------------------------------
# Motor Generico de Payoff al Vencimiento (§4.1)
# ---------------------------------------------------------------------------
def calculate_generic_payoff(
    legs: list[dict[str, Any]],
    entry_net_per_share: float,
    costs_total: float,
    s_prices: list[float],
) -> list[dict[str, float]]:
    """Calcula el P&L al vencimiento sumando algebraicamente el valor intrinseco de cada pata.
    Formula §4.1:
      valor_intrinseco_i(S_T) = max(S_T - K_i, 0) si Call; max(K_i - S_T, 0) si Put
      P&L(S_T) = sum_i(lado_i * ratio_i * M_i * (valor_intrinseco_i(S_T) - prima_i)) - costes
    """
    results: list[dict[str, float]] = []
    for s_t in s_prices:
        pnl = 0.0
        for leg in legs:
            side = 1.0 if leg["side"] == "buy" else -1.0
            ratio = float(leg.get("ratio", 1.0))
            mult = float(leg.get("multiplier", 100))
            k = float(leg["strike"])
            right = leg["right"].upper()
            premium = float(leg.get("exec_price") or leg.get("mid") or 0.0)

            intrinsic = max(s_t - k, 0.0) if right == "C" else max(k - s_t, 0.0)
            pnl += side * ratio * mult * (intrinsic - premium)

        # Restar comisiones y slippage de ida y vuelta
        net_pnl = pnl - costs_total
        results.append({"price": round(s_t, 4), "pnl": round(net_pnl, 2)})
    return results


# ---------------------------------------------------------------------------
# Oraculo de Formulas Cerradas (§4.2)
# ---------------------------------------------------------------------------
def closed_formula_oracle(
    strategy_key: str,
    legs: list[dict[str, Any]],
    costs_total: float = 0.0,
    multiplier: int = 100,
) -> dict[str, Any]:
    """Calcula analiticamente pérdida máxima, ganancia máxima y break-even segun §4.2."""
    if not legs:
        return {"max_loss": 0.0, "max_profit": 0.0, "breakeven": []}

    m = float(multiplier)

    if strategy_key in ("long_call", "long_put"):
        l = legs[0]
        k = float(l["strike"])
        premium = float(l.get("exec_price") or l.get("mid") or 0.0)
        max_loss = premium * m + costs_total
        be = k + (premium + costs_total / m) if l["right"] == "C" else k - (premium + costs_total / m)
        max_profit = None if l["right"] == "C" else (k - premium) * m - costs_total
        return {"max_loss": round(max_loss, 2), "max_profit": max_profit, "breakeven": [round(be, 4)]}

    elif strategy_key == "bull_call_spread":
        # Compra K1, vende K2 (K1 < K2)
        l_buy = next(l for l in legs if l["side"] == "buy")
        l_sell = next(l for l in legs if l["side"] == "sell")
        k1, k2 = float(l_buy["strike"]), float(l_sell["strike"])
        w = k2 - k1
        debit = float(l_buy.get("exec_price") or 0.0) - float(l_sell.get("exec_price") or 0.0)
        max_loss = debit * m + costs_total
        max_profit = (w - debit) * m - costs_total
        be = k1 + debit + (costs_total / m)
        return {"max_loss": round(max_loss, 2), "max_profit": round(max_profit, 2), "breakeven": [round(be, 4)]}

    elif strategy_key == "bear_put_spread":
        # Compra K2, vende K1 (K1 < K2)
        l_buy = next(l for l in legs if l["side"] == "buy")
        l_sell = next(l for l in legs if l["side"] == "sell")
        k2, k1 = float(l_buy["strike"]), float(l_sell["strike"])
        w = k2 - k1
        debit = float(l_buy.get("exec_price") or 0.0) - float(l_sell.get("exec_price") or 0.0)
        max_loss = debit * m + costs_total
        max_profit = (w - debit) * m - costs_total
        be = k2 - debit - (costs_total / m)
        return {"max_loss": round(max_loss, 2), "max_profit": round(max_profit, 2), "breakeven": [round(be, 4)]}

    elif strategy_key == "bull_put_spread":
        # Vende K2, compra K1 (K1 < K2). Recibe Credito C = bid(K2) - ask(K1)
        l_sell = next(l for l in legs if l["side"] == "sell")
        l_buy = next(l for l in legs if l["side"] == "buy")
        k2, k1 = float(l_sell["strike"]), float(l_buy["strike"])
        w = k2 - k1
        credit = float(l_sell.get("exec_price") or 0.0) - float(l_buy.get("exec_price") or 0.0)
        max_loss = (w - credit) * m + costs_total
        max_profit = credit * m - costs_total
        be = k2 - credit + (costs_total / m)
        return {"max_loss": round(max_loss, 2), "max_profit": round(max_profit, 2), "breakeven": [round(be, 4)]}

    elif strategy_key == "bear_call_spread":
        # Vende K1, compra K2 (K1 < K2). Recibe Credito C = bid(K1) - ask(K2)
        l_sell = next(l for l in legs if l["side"] == "sell")
        l_buy = next(l for l in legs if l["side"] == "buy")
        k1, k2 = float(l_sell["strike"]), float(l_buy["strike"])
        w = k2 - k1
        credit = float(l_sell.get("exec_price") or 0.0) - float(l_buy.get("exec_price") or 0.0)
        max_loss = (w - credit) * m + costs_total
        max_profit = credit * m - costs_total
        be = k1 + credit - (costs_total / m)
        return {"max_loss": round(max_loss, 2), "max_profit": round(max_profit, 2), "breakeven": [round(be, 4)]}

    elif strategy_key == "long_straddle":
        k = float(legs[0]["strike"])
        tot_premium = sum(float(l.get("exec_price") or 0.0) for l in legs)
        max_loss = tot_premium * m + costs_total
        be1 = k - tot_premium - (costs_total / m)
        be2 = k + tot_premium + (costs_total / m)
        return {"max_loss": round(max_loss, 2), "max_profit": None, "breakeven": [round(be1, 4), round(be2, 4)]}

    elif strategy_key == "long_strangle":
        put_leg = next(l for l in legs if l["right"] == "P")
        call_leg = next(l for l in legs if l["right"] == "C")
        k_put, k_call = float(put_leg["strike"]), float(call_leg["strike"])
        tot_premium = float(put_leg.get("exec_price") or 0.0) + float(call_leg.get("exec_price") or 0.0)
        max_loss = tot_premium * m + costs_total
        be1 = k_put - tot_premium - (costs_total / m)
        be2 = k_call + tot_premium + (costs_total / m)
        return {"max_loss": round(max_loss, 2), "max_profit": None, "breakeven": [round(be1, 4), round(be2, 4)]}

    return {"max_loss": 0.0, "max_profit": 0.0, "breakeven": []}
