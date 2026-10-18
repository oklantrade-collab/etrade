"""Pruebas del Sprint 5: Options Score, Rankings y Selector de Cartera con restricciones.
Verifica:
  1. Propiedades matematicas del score (escala 0-100, monotonias, pesos).
  2. Penalizaciones y bonificaciones (EV, APEX, liquidez, datos LIVE vs DELAYED, IV/griegas, eventos).
  3. Determinismo y reproducibilidad de rankings globales y por estrategia.
  4. Selector de cartera greedy con todas las restricciones (§11.1 y §12):
     - Deduplicacion por subyacente (max 1 por ticker).
     - Limite de direccion (max 2 bullish / bearish).
     - Presupuesto de riesgo abierto (ej. 50 + 25 + 25 <= 100).
     - Techo individual por operacion (50-100 USD).
     - Stop diario (bloquea nuevas selecciones por PnL marcado, no riesgo teorico).
     - Adaptacion de tamano (qty) hacia abajo si no cabe en el presupuesto restante.
     - Cupo diario maximo de selecciones.
"""
from __future__ import annotations

import pytest
from app.options import options_aduana as aduana
from app.options import portfolio_selector as sel
from app.options import score as sc
from app.options import settings_defaults as sd

EFF = sd.effective_settings(None)


def mock_cand(id_: int, uid: int, strat: str = "bull_call_spread", direction: str = "bullish",
              ev_ratio: float = 0.20, loss: float = 40.0, score_override: float | None = None,
              qty: int = 1, contract_loss: float | None = None, **kw) -> dict:
    c_loss = contract_loss if contract_loss is not None else loss / qty
    cand = {
        "id": id_,
        "underlying_id": uid,
        "strategy_type": strat,
        "direction": direction,
        "direction_source": kw.get("direction_source", "apex"),
        "expiry": "2026-11-20",
        "qty": qty,
        "entry_debit": 0.40,
        "max_loss_contract": c_loss,
        "max_loss_total": loss,
        "max_profit_contract": 60.0,
        "breakeven": 20.40,
        "costs_contract": 4.80,
        "exec_overcost_pct": kw.get("exec_overcost_pct", 5.0),
        "ev_neutral_net": -5.0,
        "ev_view_net": loss * ev_ratio,
        "ev_view_adverse": loss * ev_ratio * 0.8,
        "ev_ratio": ev_ratio,
        "worst_adverse_scenario_pnl": -loss * 0.8,
        "pop_neutral": 0.45,
        "pop_view": 0.58,
        "eligibility_status": "eligible",
        "legs": kw.get("legs", [
            {"strike": 20, "side": "buy", "right": "C", "bid": 0.98, "ask": 1.00, "iv": 0.35, "delta": 0.52,
             "open_interest": 1000, "market_data_type": "LIVE"},
            {"strike": 21, "side": "sell", "right": "C", "bid": 0.58, "ask": 0.60, "iv": 0.33, "delta": 0.30,
             "open_interest": 800, "market_data_type": "LIVE"},
        ]),
    }
    cand.update(kw)
    if score_override is not None:
        cand["score"] = score_override
    return cand


def mock_und(uid: int, symbol: str, apex_score: float = 75.0, direction: str = "bullish", **kw) -> dict:
    u = {
        "id": uid,
        "symbol": symbol,
        "price": 20.0,
        "apex_score": apex_score,
        "direction": direction,
        "optionable": True,
        "data_state": "LIVE",
        "event_flags": [],
        "warnings": [],
    }
    u.update(kw)
    return u


# ====================================================================== 1. Score
def test_score_is_normalized_between_0_and_100():
    c = mock_cand(1, 1, ev_ratio=0.15)
    u = mock_und(1, "SPY")
    res = sc.score_candidate(c, u, EFF)
    assert 0.0 <= res["score"] <= 100.0
    bd = res["score_breakdown"]
    for comp in bd["components"].values():
        assert 0.0 <= comp["score"] <= 100.0


def test_expectancy_monotonicity_and_anchor():
    u = mock_und(1, "SPY")
    c_zero = mock_cand(1, 1, ev_ratio=-0.05)
    c_mid = mock_cand(2, 1, ev_ratio=0.15)
    c_anchor = mock_cand(3, 1, ev_ratio=0.30)
    c_high = mock_cand(4, 1, ev_ratio=0.50)

    s0, _ = sc.compute_expectancy_score(c_zero, EFF)
    sm, _ = sc.compute_expectancy_score(c_mid, EFF)
    sa, _ = sc.compute_expectancy_score(c_anchor, EFF)
    sh, _ = sc.compute_expectancy_score(c_high, EFF)

    assert s0 == 0.0
    assert 0.0 < sm < 100.0
    assert sa == 100.0
    assert sh == 100.0  # clip en anchor


def test_apex_signal_alignment_and_contradiction():
    u_bull = mock_und(1, "SPY", apex_score=80.0, direction="bullish")
    c_bull = mock_cand(1, 1, direction="bullish", direction_source="apex")
    c_bear = mock_cand(2, 1, direction="bearish", direction_source="apex")
    c_unver = mock_cand(3, 1, direction="bullish", direction_source="unverified")

    s_align, _ = sc.compute_apex_signal_score(c_bull, u_bull)
    s_contra, _ = sc.compute_apex_signal_score(c_bear, u_bull)
    s_unver, _ = sc.compute_apex_signal_score(c_unver, u_bull)

    assert s_align == 80.0
    assert s_contra == 0.0   # contradiccion penalizada totalmente
    assert s_unver < s_align  # penalizacion por no verificada


def test_liquidity_spread_and_open_interest():
    eff = dict(EFF, allow_delayed_data=True)
    # Tight spread (1%), high OI (1000)
    c_tight = mock_cand(1, 1)
    s_tight, _ = sc.compute_liquidity_score(c_tight, eff)

    # Wide spread (8%)
    c_wide = mock_cand(2, 1, legs=[
        {"strike": 20, "side": "buy", "right": "C", "bid": 0.92, "ask": 1.00, "open_interest": 100, "market_data_type": "LIVE"},
        {"strike": 21, "side": "sell", "right": "C", "bid": 0.52, "ask": 0.60, "open_interest": 100, "market_data_type": "LIVE"},
    ])
    s_wide, _ = sc.compute_liquidity_score(c_wide, eff)
    assert s_tight > s_wide


def test_liquidity_delayed_vs_live_data():
    eff_allow = dict(EFF, allow_delayed_data=True)
    eff_block = dict(EFF, allow_delayed_data=False)
    c_delayed = mock_cand(1, 1, legs=[
        {"strike": 20, "side": "buy", "right": "C", "bid": 0.98, "ask": 1.00, "open_interest": 1000, "market_data_type": "DELAYED"},
        {"strike": 21, "side": "sell", "right": "C", "bid": 0.58, "ask": 0.60, "open_interest": 800, "market_data_type": "DELAYED"},
    ])

    s_allowed, d_allowed = sc.compute_liquidity_score(c_delayed, eff_allow)
    s_blocked, _ = sc.compute_liquidity_score(c_delayed, eff_block)

    assert s_allowed > 0.0
    assert d_allowed["data_multiplier"] == 0.70  # penalizacion 30% en modo prueba
    assert s_blocked == 0.0                      # rechazado si no se permite


def test_iv_crush_penalty_and_delta():
    c_low_iv = mock_cand(1, 1, legs=[
        {"strike": 20, "side": "buy", "right": "C", "bid": 0.98, "ask": 1.00, "iv": 0.25, "delta": 0.50},
        {"strike": 21, "side": "sell", "right": "C", "bid": 0.58, "ask": 0.60, "iv": 0.25, "delta": 0.30},
    ])
    c_high_iv = mock_cand(2, 1, legs=[
        {"strike": 20, "side": "buy", "right": "C", "bid": 0.98, "ask": 1.00, "iv": 0.95, "delta": 0.50},
        {"strike": 21, "side": "sell", "right": "C", "bid": 0.58, "ask": 0.60, "iv": 0.95, "delta": 0.30},
    ])
    s_low, _ = sc.compute_iv_greeks_score(c_low_iv)
    s_high, _ = sc.compute_iv_greeks_score(c_high_iv)
    assert s_low > s_high


def test_context_event_score():
    u_clean = mock_und(1, "SPY", event_flags=[])
    u_event = mock_und(2, "AAPL", event_flags=["earnings"])
    u_unver = mock_und(3, "MSFT", event_flags=None, warnings=["eventos no verificados"])
    c = mock_cand(1, 1)

    s_clean, _ = sc.compute_context_score(c, u_clean, EFF)
    s_event, _ = sc.compute_context_score(c, u_event, EFF)
    s_unver, _ = sc.compute_context_score(c, u_unver, EFF)

    assert s_clean == 100.0
    assert s_event == 0.0
    assert s_unver == 50.0


# ====================================================================== 2. Ranking & Determinismo
def test_ranking_is_strictly_deterministic_and_reproducible():
    unds = {1: mock_und(1, "AAPL", apex_score=85), 2: mock_und(2, "MSFT", apex_score=70), 3: mock_und(3, "GOOGL", apex_score=90)}
    cands = [
        mock_cand(101, 1, "bull_call_spread", ev_ratio=0.10),
        mock_cand(102, 2, "bull_call_spread", ev_ratio=0.25),
        mock_cand(103, 3, "long_call", ev_ratio=0.20),
    ]

    run1 = sc.rank_and_score_candidates(cands, unds, EFF)
    run2 = sc.rank_and_score_candidates(cands, unds, EFF)

    # Identicos ranks y scores
    assert [r["id"] for r in run1] == [r["id"] for r in run2]
    assert [r["score"] for r in run1] == [r["score"] for r in run2]
    assert [r["rank_global"] for r in run1] == [1, 2, 3]

    # Orden descendente por score
    scores = [r["score"] for r in run1]
    assert scores == sorted(scores, reverse=True)


# ====================================================================== 3. Selector de Cartera
def test_selector_respects_single_position_per_underlying():
    # Dos candidatas para el mismo subyacente (uid 1)
    c1 = mock_cand(1, 1, score_override=85.0, loss=40.0)
    c2 = mock_cand(2, 1, score_override=75.0, loss=35.0)

    res = sel.select_portfolio([c1, c2], [], EFF)
    assert len(res.selected) == 1
    assert res.selected[0]["id"] == 1
    assert len(res.skipped) == 1
    assert "ya tiene posicion o seleccion activa" in res.skipped[0]["reason"]


def test_selector_respects_max_same_direction_limit():
    # Limite = 2 en la misma direccion
    c1 = mock_cand(1, 1, direction="bullish", score_override=90.0, loss=30.0)
    c2 = mock_cand(2, 2, direction="bullish", score_override=85.0, loss=30.0)
    c3 = mock_cand(3, 3, direction="bullish", score_override=80.0, loss=30.0)
    c4 = mock_cand(4, 4, direction="bearish", score_override=78.0, loss=30.0)

    eff = dict(EFF, max_same_direction=2, max_daily_selections=5)
    res = sel.select_portfolio([c1, c2, c3, c4], [], eff)

    # Debe seleccionar c1, c2 y c4 (pero saltar c3 por direccion)
    selected_ids = [c["id"] for c in res.selected]
    assert selected_ids == [1, 2, 4]
    skipped_c3 = next(s for s in res.skipped if s["candidate_id"] == 3)
    assert "Limite de 2 posiciones en direccion 'bullish'" in skipped_c3["reason"]


def test_selector_open_risk_budget_packing_example_50_25_25():
    # Presupuesto abierto 100 USD. Posicion abierta existente de 50 USD.
    # Restante = 50 USD. Candidatas: c1=25, c2=25, c3=25.
    existing = [aduana.OpenPosition(underlying_id=99, max_loss_total=50.0, direction="bearish")]
    c1 = mock_cand(1, 1, score_override=90.0, loss=25.0)
    c2 = mock_cand(2, 2, score_override=85.0, loss=25.0)
    c3 = mock_cand(3, 3, score_override=80.0, loss=25.0)

    eff = dict(EFF, max_open_risk_usd=100.0, max_same_direction=5, max_daily_selections=5)
    res = sel.select_portfolio([c1, c2, c3], existing, eff)

    assert len(res.selected) == 2
    assert [c["id"] for c in res.selected] == [1, 2]
    assert res.total_risk_allocated == 50.0
    assert res.remaining_budget == 0.0

    skipped_c3 = next(s for s in res.skipped if s["candidate_id"] == 3)
    assert "excede presupuesto restante" in skipped_c3["reason"]


def test_selector_adapts_qty_when_candidate_exceeds_remaining_budget():
    # Presupuesto restante = 30 USD.
    # Candidata con qty=2, contrato=20 USD, total=40 USD (> 30).
    # Regla 4 de §11.1: si contract_loss (20) <= 30, adapta qty a 1 (20 USD)!
    c = mock_cand(1, 1, score_override=85.0, loss=40.0, qty=2, contract_loss=20.0)

    eff = dict(EFF, max_open_risk_usd=30.0)
    res = sel.select_portfolio([c], [], eff)

    assert len(res.selected) == 1
    sel_cand = res.selected[0]
    assert sel_cand["qty"] == 1
    assert sel_cand["max_loss_total"] == 20.0
    assert sel_cand["budget_adapted"] is True
    assert res.remaining_budget == 10.0


def test_selector_daily_stop_blocks_all_selections():
    # Stop diario = 50 USD. PnL acumulado = -55 USD.
    c1 = mock_cand(1, 1, score_override=95.0, loss=20.0)
    c2 = mock_cand(2, 2, score_override=90.0, loss=20.0)

    eff = dict(EFF, daily_stop_usd=50.0)
    res = sel.select_portfolio([c1, c2], [], eff, realized_pnl_today=-40.0, unrealized_pnl_today=-15.0)

    assert res.daily_stop_triggered is True
    assert len(res.selected) == 0
    assert len(res.skipped) == 2
    assert "Stop diario activado" in res.stop_reason


def test_selector_respects_single_trade_cap():
    # Cap por operacion = 50 USD. Candidata con riesgo = 60 USD (qty=1).
    c = mock_cand(1, 1, score_override=85.0, loss=60.0, qty=1, contract_loss=60.0)
    eff = dict(EFF, max_risk_per_trade_usd=50.0)

    res = sel.select_portfolio([c], [], eff)
    assert len(res.selected) == 0
    assert "supera maximo ($50.00)" in res.skipped[0]["reason"]


def test_selector_filters_below_min_score():
    c_good = mock_cand(1, 1, score_override=65.0, loss=30.0)
    c_low = mock_cand(2, 2, score_override=55.0, loss=30.0)

    eff = dict(EFF, min_score=60.0)
    res = sel.select_portfolio([c_good, c_low], [], eff)

    assert len(res.selected) == 1
    assert res.selected[0]["id"] == 1
    assert "inferior al minimo requerido (60.0)" in res.skipped[0]["reason"]
