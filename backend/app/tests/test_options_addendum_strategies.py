"""Pruebas del Addendum v1.1: Estrategias adicionales de opciones, catalogo maestro,
motor generico de payoff vs oraculo analitico, verticales de credito (Bull Put / Bear Call),
filtro de costes/riesgo y regla O-13 de ADUANA.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import pytest

from app.options import options_aduana as aduana
from app.options import settings_defaults as sd
from app.options import strategies as st
from app.options.strategies_catalog import (
    STRATEGY_CATALOG,
    calculate_generic_payoff,
    closed_formula_oracle,
    get_all_strategies,
    get_viable_strategies_for_capital,
)

EFF = sd.effective_settings(None)
TODAY = date(2026, 11, 20)
EXPIRY = date(2026, 12, 18)


# ----------------------------------------------------------------------
# 1. Catalogo Maestro (14 estrategias y viabilidad de capital)
# ----------------------------------------------------------------------
def test_strategy_catalog_contains_14_strategies():
    assert len(STRATEGY_CATALOG) == 14
    keys = set(STRATEGY_CATALOG.keys())
    expected = {
        "long_call", "long_put", "bull_call_spread", "bear_put_spread",
        "bull_put_spread", "bear_call_spread", "long_straddle", "long_strangle",
        "iron_condor", "iron_butterfly", "long_call_butterfly", "long_put_butterfly",
        "calendar_spread", "diagonal_spread",
    }
    assert keys == expected


def test_strategy_catalog_families():
    # Familias estrictas segun §3 del Addendum
    assert STRATEGY_CATALOG["long_call"].family == "single-leg"
    assert STRATEGY_CATALOG["long_put"].family == "single-leg"
    assert STRATEGY_CATALOG["bull_call_spread"].family == "vertical"
    assert STRATEGY_CATALOG["bear_put_spread"].family == "vertical"
    assert STRATEGY_CATALOG["bull_put_spread"].family == "vertical"
    assert STRATEGY_CATALOG["bear_call_spread"].family == "vertical"
    assert STRATEGY_CATALOG["iron_condor"].family == "multi-leg defined-risk"
    assert STRATEGY_CATALOG["calendar_spread"].family == "calendar/diagonal"


def test_capital_viability_filter_50_usd():
    viable = get_viable_strategies_for_capital(50.0)
    # Con $50 de riesgo maximo y $3.40 de costes por contrato:
    # 4 contratos (Condor, Butterfly) cuestan $13.60 = 27.2% del riesgo (supera 20% max)
    # Por tanto solo single-leg y verticales de 2 patas caben dentro de $50 y del 20% de costes
    assert set(viable) == {
        "long_call", "long_put", "bull_call_spread", "bear_put_spread",
        "bull_put_spread", "bear_call_spread"
    }


# ----------------------------------------------------------------------
# 2. Motor Genérico de Payoff vs Oráculo Analítico (§4.1 y §4.2)
# ----------------------------------------------------------------------
def test_payoff_generic_vs_oracle_bull_call_spread():
    # Long Call K1=100 @ 3.0, Short Call K2=105 @ 1.0 (debit = 2.0). Costes = 6.80
    legs = [
        {"side": "buy", "right": "C", "strike": 100.0, "exec_price": 3.0, "ratio": 1.0, "multiplier": 100},
        {"side": "sell", "right": "C", "strike": 105.0, "exec_price": 1.0, "ratio": 1.0, "multiplier": 100},
    ]
    costs = 6.80
    oracle = closed_formula_oracle("bull_call_spread", legs, costs_total=costs)
    # debit = 2.0; width = 5.0
    # max_loss = 2.0 * 100 + 6.80 = 206.80
    # max_profit = (5 - 2) * 100 - 6.80 = 293.20
    # be = 100 + 2.0 + 0.068 = 102.068
    assert oracle["max_loss"] == 206.80
    assert oracle["max_profit"] == 293.20
    assert oracle["breakeven"] == [102.068]

    # Evaluamos en una malla de precios
    mesh = [80.0, 95.0, 100.0, 102.068, 105.0, 120.0]
    curve = calculate_generic_payoff(legs, entry_net_per_share=0.0, costs_total=costs, s_prices=mesh)
    curve_dict = {pt["price"]: pt["pnl"] for pt in curve}

    # Precios <= 100: perdida maxima constante
    assert curve_dict[80.0] == -206.80
    assert curve_dict[100.0] == -206.80

    # Break-even: P&L cercano a 0
    assert abs(curve_dict[102.068]) < 0.05

    # Precios >= 105: ganancia maxima constante
    assert curve_dict[105.0] == 293.20
    assert curve_dict[120.0] == 293.20


def test_payoff_generic_vs_oracle_bull_put_spread():
    # Vertical de credito: vende Put K2=105 @ 2.50 (bid), compra Put K1=100 @ 1.00 (ask)
    # Credit C = 1.50, Width W = 5.0, Costs = 6.80
    legs = [
        {"side": "sell", "right": "P", "strike": 105.0, "exec_price": 2.50, "ratio": 1.0, "multiplier": 100},
        {"side": "buy", "right": "P", "strike": 100.0, "exec_price": 1.00, "ratio": 1.0, "multiplier": 100},
    ]
    costs = 6.80
    oracle = closed_formula_oracle("bull_put_spread", legs, costs_total=costs)
    # max_loss = (5 - 1.50) * 100 + 6.80 = 356.80
    # max_profit = 1.50 * 100 - 6.80 = 143.20
    # be = 105 - 1.50 + 0.068 = 103.568
    assert oracle["max_loss"] == 356.80
    assert oracle["max_profit"] == 143.20
    assert oracle["breakeven"] == [103.568]

    mesh = [80.0, 100.0, 103.568, 105.0, 120.0]
    curve = calculate_generic_payoff(legs, entry_net_per_share=0.0, costs_total=costs, s_prices=mesh)
    curve_dict = {pt["price"]: pt["pnl"] for pt in curve}

    # S <= 100: perdida maxima
    assert curve_dict[80.0] == -356.80
    assert curve_dict[100.0] == -356.80

    # Break-even
    assert abs(curve_dict[103.568]) < 0.05

    # S >= 105: ganancia maxima
    assert curve_dict[105.0] == 143.20
    assert curve_dict[120.0] == 143.20


def test_payoff_generic_vs_oracle_bear_call_spread():
    # Vertical de credito bajista: vende Call K1=100 @ 2.50, compra Call K2=105 @ 1.00
    # Credit C = 1.50, Width W = 5.0, Costs = 6.80
    legs = [
        {"side": "sell", "right": "C", "strike": 100.0, "exec_price": 2.50, "ratio": 1.0, "multiplier": 100},
        {"side": "buy", "right": "C", "strike": 105.0, "exec_price": 1.00, "ratio": 1.0, "multiplier": 100},
    ]
    costs = 6.80
    oracle = closed_formula_oracle("bear_call_spread", legs, costs_total=costs)
    # max_loss = (5 - 1.50) * 100 + 6.80 = 356.80
    # max_profit = 1.50 * 100 - 6.80 = 143.20
    # be = 100 + 1.50 - 0.068 = 101.432
    assert oracle["max_loss"] == 356.80
    assert oracle["max_profit"] == 143.20
    assert oracle["breakeven"] == [101.432]

    mesh = [90.0, 100.0, 101.432, 105.0, 120.0]
    curve = calculate_generic_payoff(legs, entry_net_per_share=0.0, costs_total=costs, s_prices=mesh)
    curve_dict = {pt["price"]: pt["pnl"] for pt in curve}

    # S <= 100: ganancia maxima
    assert curve_dict[90.0] == 143.20
    assert curve_dict[100.0] == 143.20

    # Break-even
    assert abs(curve_dict[101.432]) < 0.05

    # S >= 105: perdida maxima
    assert curve_dict[105.0] == -356.80
    assert curve_dict[120.0] == -356.80


# ----------------------------------------------------------------------
# 3. Constructor de Verticales de Crédito en strategies.py
# ----------------------------------------------------------------------
def test_build_vertical_credit_bull_put_spread_viable():
    # Cotizaciones para un Bull Put Spread viable con $50 de presupuesto:
    # Ancho W = 1.0 (K2=101, K1=100)
    # Vende K2=101 @ bid=0.78, ask=0.80 (spread 2.5% <= 10%)
    # Compra K1=100 @ bid=0.19, ask=0.20 (spread 5.0% <= 10%)
    # Credito = 0.78 - 0.20 = 0.58
    # Max loss = (1.0 - 0.58)*100 + 6.80 = 42.00 + 6.80 = 48.80 <= $50!
    # Ratio costes/riesgo = 6.80 / 48.80 = 13.9% <= 20%
    sq = st.Q(1, 101, "P", 101.0, EXPIRY, bid=0.78, ask=0.80, volume=500, open_interest=1000,
              iv=0.30, delta=-0.45, usable=True, market_data_type="LIVE")
    lq = st.Q(2, 100, "P", 100.0, EXPIRY, bid=0.19, ask=0.20, volume=500, open_interest=1000,
              iv=0.30, delta=-0.25, usable=True, market_data_type="LIVE")

    eff = dict(EFF, max_risk_per_trade_usd=50.0, spread_width_min=0.5, spread_width_max=5.0)
    cand, why = st.build_vertical_credit("bull_put_spread", sq, lq, 101.5, TODAY, eff)

    assert why == []
    assert cand is not None
    assert cand.strategy == "bull_put_spread"
    assert cand.direction == "bullish"
    assert cand.credit_or_debit == "credit"
    assert cand.family == "vertical"
    assert cand.qty == 1
    assert cand.max_loss_contract == 46.80
    assert cand.max_profit_contract == 53.20  # 0.58 * 100 - 4.80
    assert cand.entry_debit == -0.58         # negativo indica credito
    assert cand.exit_plan["short_leg_delta_exit"] == 0.70


def test_build_vertical_credit_rejects_exceeding_capital():
    # Si el spread tiene ancho W=2.0 y credito 0.60:
    # Max loss = (2.0 - 0.60)*100 + 6.80 = 146.80 > $50
    sq = st.Q(1, 102, "P", 102.0, EXPIRY, bid=0.80, ask=0.82, volume=500, open_interest=1000,
              iv=0.30, delta=-0.45, usable=True, market_data_type="LIVE")
    lq = st.Q(2, 100, "P", 100.0, EXPIRY, bid=0.18, ask=0.20, volume=500, open_interest=1000,
              iv=0.30, delta=-0.25, usable=True, market_data_type="LIVE")

    eff = dict(EFF, max_risk_per_trade_usd=50.0)
    cand, why = st.build_vertical_credit("bull_put_spread", sq, lq, 102.5, TODAY, eff)

    assert cand is None
    assert any("perdida maxima" in r and "> riesgo por operacion" in r for r in why)


def test_build_vertical_credit_rejects_inverted_strikes():
    # Bull put spread con K_short < K_long está mal construido
    sq = st.Q(1, 99, "P", 99.0, EXPIRY, bid=0.50, ask=0.52, volume=500, open_interest=1000,
              iv=0.30, delta=-0.35, usable=True, market_data_type="LIVE")
    lq = st.Q(2, 101, "P", 101.0, EXPIRY, bid=0.80, ask=0.82, volume=500, open_interest=1000,
              iv=0.30, delta=-0.45, usable=True, market_data_type="LIVE")

    cand, why = st.build_vertical_credit("bull_put_spread", sq, lq, 100.0, TODAY, EFF)
    assert cand is None
    assert "bull put spread mal construido" in why[0]


def test_cost_to_risk_ratio_rejection():
    # Si el max_loss es muy pequeño (ej. debit=0.11 -> ml = $17.80)
    # Ratio costes/riesgo = 6.80 / 17.80 = 38.2% > 20% max
    lq = st.Q(1, 100, "C", 100.0, EXPIRY, bid=0.30, ask=0.31, volume=500, open_interest=1000,
              iv=0.30, delta=0.35, usable=True, market_data_type="LIVE")
    sq = st.Q(2, 101, "C", 101.0, EXPIRY, bid=0.20, ask=0.21, volume=500, open_interest=1000,
              iv=0.30, delta=0.28, usable=True, market_data_type="LIVE")

    eff = dict(EFF, max_cost_to_risk_ratio=20.0, max_exec_overcost_pct=15.0)
    cand, why = st.build_spread("bull_call_spread", lq, sq, 100.0, TODAY, eff)
    assert cand is None
    assert any("ratio costes/riesgo" in r for r in why)


# ----------------------------------------------------------------------
# 4. Regla O-13 en ADUANA
# ----------------------------------------------------------------------
def test_aduana_rule_o13_passes_valid_candidate():
    ctx = aduana.static_context()
    cand = {
        "strategy": "bull_call_spread",
        "direction": "bullish",
        "qty": 1,
        "max_loss_contract": 45.0,
        "max_loss_total": 45.0,
        "costs_contract": 6.80,
        "entry_debit": 0.38,
        "legs": [
            {"strike": 100, "side": "buy", "right": "C", "bid": 1.0, "ask": 1.05, "market_data_type": "LIVE", "multiplier": 100, "expiry": "2026-12-18"},
            {"strike": 102, "side": "sell", "right": "C", "bid": 0.65, "ask": 0.70, "market_data_type": "LIVE", "multiplier": 100, "expiry": "2026-12-18"},
        ]
    }
    res = aduana.validate_entry(cand, ctx, EFF)
    r13 = next(r for r in res.rules if r.rule == "O-13")
    assert r13.ok is True


def test_aduana_rule_o13_rejects_nonstandard_multiplier():
    ctx = aduana.static_context()
    cand = {
        "strategy": "long_call",
        "direction": "bullish",
        "qty": 1,
        "max_loss_contract": 40.0,
        "max_loss_total": 40.0,
        "costs_contract": 3.40,
        "entry_debit": 0.36,
        "legs": [
            {"strike": 100, "side": "buy", "right": "C", "bid": 0.35, "ask": 0.36, "market_data_type": "LIVE", "multiplier": 50, "expiry": "2026-12-18"},
        ]
    }
    eff = dict(EFF, allow_nonstandard_multiplier=False)
    res = aduana.validate_entry(cand, ctx, eff)
    r13 = next(r for r in res.rules if r.rule == "O-13")
    assert r13.ok is False
    assert "multiplicador no estandar" in r13.detail


def test_aduana_rule_o13_rejects_excessive_cost_to_risk():
    ctx = aduana.static_context()
    cand = {
        "strategy": "bull_call_spread",
        "direction": "bullish",
        "qty": 1,
        "max_loss_contract": 20.0,
        "max_loss_total": 20.0,
        "costs_contract": 6.80,  # 6.80 / 20.0 = 34% > 20%
        "entry_debit": 0.13,
        "legs": [
            {"strike": 100, "side": "buy", "right": "C", "bid": 0.50, "ask": 0.52, "market_data_type": "LIVE", "multiplier": 100, "expiry": "2026-12-18"},
            {"strike": 101, "side": "sell", "right": "C", "bid": 0.38, "ask": 0.39, "market_data_type": "LIVE", "multiplier": 100, "expiry": "2026-12-18"},
        ]
    }
    eff = dict(EFF, max_cost_to_risk_ratio=20.0)
    res = aduana.validate_entry(cand, ctx, eff)
    r13 = next(r for r in res.rules if r.rule == "O-13")
    assert r13.ok is False
    assert "ratio costes/riesgo" in r13.detail
