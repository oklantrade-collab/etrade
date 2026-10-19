"""Tests de la Arquitectura Complementaria de Opciones (Doc v1.0).
Valida:
1. Maquina de estados de salud (NORMAL, DEGRADED, HALTED) y Kill Switch fail-closed.
2. Calendario Hibrido de Eventos (CLEAR_VERIFIED, EVENT_FOUND, UNKNOWN, STALE).
3. Reglas de ADUANA complementarias:
   - O-14: Calidad de datos y cobertura minima (>= 0.80).
   - O-15: Salud NORMAL y Kill Switch inactivo.
   - O-16: Revalidacion de deriva de precio (Price Drift).
4. Calculo analitico de Griegas Netas (Delta USD, Gamma, Vega punto, Theta dia).
5. Escenarios de sensibilidad de EV, ev_robust, ev_min y ev_range.
6. Score explicable con desglose de componentes y Replay determinista.
7. Restricciones de concentracion por sector y vencimiento en portfolio selector.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import pytest

from app.options import bs
from app.options import event_calendar as ec
from app.options import health
from app.options import options_aduana as aduana
from app.options import portfolio_selector as sel
from app.options import score as sc
from app.options import settings_defaults as sd
from app.options import valuation as val

EFF = sd.effective_settings(None)


# ---------------------------------------------------------------------------
# 1. System Health & Kill Switch
# ---------------------------------------------------------------------------
def test_kill_switch_blocks_open():
    """Kill Switch activado pone el estado en HALTED y bloquea can_open_new_position."""
    health.reset_health_state()
    h_normal = health.evaluate_system_health(sb=None, eff=EFF)
    assert h_normal.status == health.HealthStatus.NORMAL
    assert h_normal.can_open_new_position is True

    # Activar Kill Switch
    health.set_kill_switch(True, reason="Emergencia de prueba")
    h_halted = health.evaluate_system_health(sb=None, eff=EFF)
    assert h_halted.status == health.HealthStatus.HALTED
    assert h_halted.kill_switch_active is True
    assert h_halted.can_open_new_position is False
    assert any("Kill switch" in r for r in h_halted.reasons)

    # Limpiar
    health.reset_health_state()


def test_health_degraded_on_delayed_data_or_divergence():
    """Divergencias consecutivas o ratio alto de datos diferidos degradan a DEGRADED o HALTED."""
    health.reset_health_state()
    h_del = health.evaluate_system_health(sb=None, eff=EFF, override_delayed_ratio=0.50)
    assert h_del.status == health.HealthStatus.DEGRADED
    assert h_del.can_open_new_position is False

    h_div = health.evaluate_system_health(sb=None, eff=EFF, override_divergences=4)
    assert h_div.status == health.HealthStatus.HALTED
    assert h_div.can_open_new_position is False
    health.reset_health_state()


# ---------------------------------------------------------------------------
# 2. Hybrid Event Calendar
# ---------------------------------------------------------------------------
def test_event_calendar_states():
    """El calendario distingue CLEAR_VERIFIED, EVENT_FOUND, STALE y UNKNOWN."""
    cal = ec.HybridEventCalendar(sb=None)
    # Sin eventos verificados recientemente -> CLEAR_VERIFIED
    ev = cal.get_event("SPY", horizon_days=30)
    assert ev.state == ec.EventState.CLEAR_VERIFIED
    assert ev.is_blocking() is False

    # Mock de evento encontrado
    cal.set_mock_event("AAPL", ec.EventState.EVENT_FOUND, "earnings", date.today() + timedelta(days=2))
    ev_aapl = cal.get_event("AAPL", horizon_days=30)
    assert ev_aapl.state == ec.EventState.EVENT_FOUND
    assert ev_aapl.is_blocking() is True

    # Unknown es bloqueante en paper mode
    cal.set_mock_event("XYZ", ec.EventState.UNKNOWN)
    ev_xyz = cal.get_event("XYZ", horizon_days=30)
    assert ev_xyz.state == ec.EventState.UNKNOWN
    assert ev_xyz.is_blocking() is True


# ---------------------------------------------------------------------------
# 3. ADUANA Rules O-14, O-15, O-16
# ---------------------------------------------------------------------------
def test_rule_o14_coverage_gate():
    """O-14 rechaza si coverage < 0.80 o faltan componentes esenciales."""
    c_good = {"coverage": 1.0, "missing_components": []}
    passed, code, _ = aduana.rule_o14_coverage_and_critical_data(c_good, EFF)
    assert passed is True
    assert code == "PASS"

    c_low_cov = {"coverage": 0.65, "missing_components": ["iv_greeks", "context"]}
    passed, code, msg = aduana.rule_o14_coverage_and_critical_data(c_low_cov, EFF)
    assert passed is False
    assert code == "INSUFFICIENT_COVERAGE"

    c_miss_essential = {"coverage": 0.85, "missing_components": ["liquidity"]}
    passed, code, msg = aduana.rule_o14_coverage_and_critical_data(c_miss_essential, EFF)
    assert passed is False
    assert code == "MISSING_ESSENTIAL_COMPONENT"


def test_rule_o15_health_and_kill_switch():
    """O-15 rechaza si salud no es NORMAL o Kill Switch esta activo."""
    health.reset_health_state()
    passed, code, _ = aduana.rule_o15_system_health_and_kill_switch({}, EFF)
    assert passed is True

    health.set_kill_switch(True, reason="testing rule O-15")
    passed, code, msg = aduana.rule_o15_system_health_and_kill_switch({}, EFF)
    assert passed is False
    assert code == "SYSTEM_HALTED"
    health.reset_health_state()


def test_rule_o16_price_drift_revalidation():
    """O-16 rechaza si el subyacente o el spread se movieron > max_drift_pct."""
    cand = {"entry_debit": 1.00, "underlying_price": 100.0}
    eff_drift = dict(EFF, max_price_drift_pct=3.0)
    # Deriva leve (1%) -> PASS
    passed, code, _ = aduana.rule_o16_price_drift_revalidation(cand, 101.0, 1.01, eff_drift)
    assert passed is True

    # Deriva excesiva del subyacente (> 3% con max_drift 3.0%)
    passed, code, msg = aduana.rule_o16_price_drift_revalidation(cand, 104.0, 1.00, eff_drift)
    assert passed is False
    assert code == "PRICE_DRIFT_EXCEEDED"

    # Deriva excesiva del spread/debito (15% > 3%)
    passed, code, msg = aduana.rule_o16_price_drift_revalidation(cand, 100.0, 1.15, eff_drift)
    assert passed is False
    assert code == "PRICE_DRIFT_EXCEEDED"


# ---------------------------------------------------------------------------
# 4. Analytical Net Greeks
# ---------------------------------------------------------------------------
def test_analytical_bs_greeks():
    """Verifica formulas analiticas de Gamma, Vega y Theta."""
    S, K, T, r, sigma = 100.0, 100.0, 30.0 / 365.0, 0.04, 0.30
    gamma = bs.bs_gamma(S, K, T, r, sigma)
    vega = bs.bs_vega(S, K, T, r, sigma)
    theta_c = bs.bs_theta(S, K, T, r, sigma, "C")
    theta_p = bs.bs_theta(S, K, T, r, sigma, "P")

    assert gamma is not None and gamma > 0
    assert vega is not None and vega > 0  # Vega positivo para opciones compradas
    assert theta_c is not None and theta_c < 0  # Decaimiento temporal negativo
    assert theta_p is not None and theta_p < 0


def test_valuation_computes_net_greeks_and_sensitivities():
    """value_candidate() calcula greeks_net, sensitivities, ev_min, ev_range y ev_robust."""
    today = date(2026, 11, 1)
    cand = {
        "expiry": "2026-11-20",
        "direction": "bullish",
        "entry_debit": 0.50,
        "costs_contract": 4.80,
        "max_loss_contract": 50.0,
        "legs": [
            {"strike": 100, "side": "buy", "right": "C", "bid": 2.10, "ask": 2.15, "iv": 0.30},
            {"strike": 105, "side": "sell", "right": "C", "bid": 0.70, "ask": 0.75, "iv": 0.28},
        ],
    }
    res = val.value_candidate(cand, S0=100.0, eff=EFF, today=today, direction_verified=True)
    assert "error" not in res
    assert "greeks_net" in res and res["greeks_net"] is not None
    gn = res["greeks_net"]
    assert "delta_shares" in gn and "delta_usd" in gn and "gamma" in gn and "vega_point" in gn and "theta_day" in gn
    assert gn["delta_shares"] > 0  # Bull call spread tiene delta positivo

    assert "sensitivities" in res
    sens = res["sensitivities"]
    assert "base" in sens and "reduced_bias" in sens and "no_bias" in sens and "adverse_exec" in sens
    assert "ev_robust" in res
    assert "ev_range" in res


# ---------------------------------------------------------------------------
# 5. Explainable Score & Replay
# ---------------------------------------------------------------------------
def test_score_explainable_breakdown_and_replay():
    """Score genera JSON explicable con lista de componentes y permite Replay determinista."""
    cand = {
        "id": 42,
        "direction": "bullish",
        "direction_source": "apex",
        "ev_ratio": 0.25,
        "ev_view_net": 12.5,
        "max_loss_contract": 50.0,
        "max_loss_total": 50.0,
        "worst_adverse_scenario_pnl": -35.0,
        "exec_overcost_pct": 5.0,
        "legs": [
            {"strike": 100, "side": "buy", "right": "C", "bid": 2.10, "ask": 2.15, "iv": 0.30, "open_interest": 800, "market_data_type": "LIVE"},
        ],
    }
    und = {"direction": "bullish", "apex_score": 75.0, "event_flags": []}
    res = sc.score_candidate(cand, und, EFF)
    assert "score" in res
    assert "coverage" in res
    assert res["coverage"] == 1.0  # Todos los componentes presentes

    b = res["score_breakdown"]
    assert "components_list" in b
    assert len(b["components_list"]) == 6
    names = [c["name"] for c in b["components_list"]]
    assert names == ["expectancy", "apex_signal", "liquidity", "risk", "iv_greeks", "context"]

    # Replay determinista (§13.3)
    cand_with_score = dict(cand, score=res["score"])
    rep = sc.replay_evaluation(cand_with_score, und, EFF)
    assert rep["matches"] is True
    assert rep["diff"] == 0.0


# ---------------------------------------------------------------------------
# 6. Portfolio Selector Sector & Expiry Concentration
# ---------------------------------------------------------------------------
def test_portfolio_selector_sector_and_expiry_limits():
    """Selector respeta limite de max 2 por sector y max 2 por vencimiento."""
    c1 = {
        "id": 1, "underlying_id": 101, "symbol": "AAPL", "direction": "bullish",
        "sector": "Technology", "expiry": "2026-11-20", "score": 85.0,
        "ev_ratio": 0.25, "max_loss_total": 20.0, "max_loss_contract": 20.0,
        "qty": 1, "eligibility_status": "eligible",
    }
    c2 = {
        "id": 2, "underlying_id": 102, "symbol": "MSFT", "direction": "bullish",
        "sector": "Technology", "expiry": "2026-11-20", "score": 80.0,
        "ev_ratio": 0.22, "max_loss_total": 20.0, "max_loss_contract": 20.0,
        "qty": 1, "eligibility_status": "eligible",
    }
    # Tercera con el mismo sector (Technology) debe ser descartada por limite de sector
    c3 = {
        "id": 3, "underlying_id": 103, "symbol": "NVDA", "direction": "neutral",
        "sector": "Technology", "expiry": "2026-12-18", "score": 78.0,
        "ev_ratio": 0.20, "max_loss_total": 20.0, "max_loss_contract": 20.0,
        "qty": 1, "eligibility_status": "eligible",
    }
    # Cuarta de otro sector pero misma fecha de vencimiento que las 2 primeras -> descartada por vencimiento
    c4 = {
        "id": 4, "underlying_id": 104, "symbol": "JPM", "direction": "neutral",
        "sector": "Financials", "expiry": "2026-11-20", "score": 75.0,
        "ev_ratio": 0.18, "max_loss_total": 20.0, "max_loss_contract": 20.0,
        "qty": 1, "eligibility_status": "eligible",
    }
    # Quinta de otro sector y otro vencimiento -> seleccionada
    c5 = {
        "id": 5, "underlying_id": 105, "symbol": "XOM", "direction": "neutral",
        "sector": "Energy", "expiry": "2026-12-18", "score": 72.0,
        "ev_ratio": 0.16, "max_loss_total": 20.0, "max_loss_contract": 20.0,
        "qty": 1, "eligibility_status": "eligible",
    }

    res = sel.select_portfolio([c1, c2, c3, c4, c5], existing_positions=[], eff=EFF)
    selected_ids = [c["id"] for c in res.selected]
    assert 1 in selected_ids
    assert 2 in selected_ids
    assert 3 not in selected_ids  # bloqueado por sector Technology (2 ya elegidos)
    assert 4 not in selected_ids  # bloqueado por vencimiento 2026-11-20 (2 ya elegidos)
    assert 5 in selected_ids      # permitido (Energy, 2026-12-18)
