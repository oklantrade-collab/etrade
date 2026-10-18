"""Pruebas del Sprint 7: Performance Analytics, Calibracion de Probabilidad, Alpha y Gate G3.
Verifica:
  1. Metricas financieras de la cartera (PnL neto, profit factor, win rate, expectancy, drawdown).
  2. Sensibilidad a slippage (1x vs 2x vs 3x).
  3. Calibracion de probabilidad binned (diagrama de confiabilidad, Brier score, error por tramo).
  4. Estimacion empirica bayesiana de alpha vs prior teorico.
  5. Sonda y evaluador del Gate G3 con los 5 criterios (duracion shadow, trades, expectancy, calibracion, DD).
  6. Determinismo y robustez ante listas vacias o datos atipicos.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import pytest

from app.options import calibration as cal
from app.options import g3_probe as g3
from app.options import performance as perf
from app.options import settings_defaults as sd

EFF = sd.effective_settings(None)


def mock_trade(id_: int, pnl: float, pop: float = 0.55, strat: str = "bull_call_spread",
               symbol: str = "SPY", entry_dt: str = "2026-10-01T14:00:00+00:00",
               exit_dt: str = "2026-10-01T19:00:00+00:00", slip: float = 0.005) -> dict:
    return {
        "id": id_,
        "symbol": symbol,
        "strategy_type": strat,
        "direction": "bullish",
        "qty": 1,
        "status": "closed",
        "realized_pnl": pnl,
        "entry_time": entry_dt,
        "exit_time": exit_dt,
        "exit_reason": "take_profit" if pnl > 0 else "stop_loss",
        "candidate": {
            "pop_view": pop,
            "pop_neutral": 0.50,
            "ev_view_net": 5.0,
        },
        "entry_fills": [{"slippage_applied": slip}],
        "exit_fills": [{"slippage_applied": slip}],
    }


# ====================================================================== 1. Performance
def test_performance_handles_empty_trades_gracefully():
    res = perf.calculate_performance([])
    assert res["total_trades"] == 0
    assert res["net_pnl_usd"] == 0.0
    assert res["profit_factor"] == 0.0
    assert res["win_rate_pct"] == 0.0
    assert res["equity_curve"] == []


def test_performance_computes_exact_pnl_expectancy_and_profit_factor():
    # 3 trades: +30, -10, +10 -> Total = +30, Expectancy = +10, Gross Win = 40, Gross Loss = 10, PF = 4.0, WR = 66.67%
    trades = [
        mock_trade(1, 30.0),
        mock_trade(2, -10.0),
        mock_trade(3, 10.0),
    ]
    res = perf.calculate_performance(trades)
    assert res["total_trades"] == 3
    assert res["winning_trades"] == 2
    assert res["losing_trades"] == 1
    assert res["net_pnl_usd"] == 30.0
    assert res["expectancy_usd"] == 10.0
    assert res["gross_profit_usd"] == 40.0
    assert res["gross_loss_usd"] == 10.0
    assert res["profit_factor"] == 4.0
    assert res["win_rate_pct"] == pytest.approx(66.67, abs=0.01)


def test_performance_computes_max_drawdown_chronologically():
    # Equity path:
    # Trade 1: +50 -> Peak 50, DD 0
    # Trade 2: -30 -> Cum 20, Peak 50, DD 30
    # Trade 3: -10 -> Cum 10, Peak 50, DD 40 (Max DD)
    # Trade 4: +60 -> Cum 70, Peak 70, DD 0
    # Trade 5: -25 -> Cum 45, Peak 70, DD 25
    trades = [
        mock_trade(1, 50.0, exit_dt="2026-10-01T15:00:00+00:00"),
        mock_trade(2, -30.0, exit_dt="2026-10-02T15:00:00+00:00"),
        mock_trade(3, -10.0, exit_dt="2026-10-03T15:00:00+00:00"),
        mock_trade(4, 60.0, exit_dt="2026-10-04T15:00:00+00:00"),
        mock_trade(5, -25.0, exit_dt="2026-10-05T15:00:00+00:00"),
    ]
    res = perf.calculate_performance(trades)
    assert res["max_drawdown_usd"] == 40.0
    assert len(res["equity_curve"]) == 5
    assert res["equity_curve"][2]["drawdown"] == 40.0


def test_performance_slippage_sensitivity():
    trades = [
        mock_trade(1, 20.0, slip=0.01),  # 2 fills * 0.01 * 100 = $2.00 base slip
        mock_trade(2, 20.0, slip=0.01),  # $2.00 base slip
    ]
    res = perf.calculate_performance(trades)
    assert res["net_pnl_usd"] == 40.0
    assert res["slippage_sensitivity"]["base_slippage_usd"] == 4.0
    assert res["slippage_sensitivity"]["pnl_with_2x_slippage"] == 36.0
    assert res["slippage_sensitivity"]["pnl_with_3x_slippage"] == 32.0


# ====================================================================== 2. Calibracion de Probabilidad & Alpha
def test_calibration_binned_diagram_and_brier_score():
    # 10 trades en el tramo 0.60-0.80 (POP media 0.70)
    # 7 ganadores (70% win rate) -> error ~0.0%
    trades = [
        mock_trade(i, 20.0 if i <= 7 else -20.0, pop=0.70)
        for i in range(1, 11)
    ]
    res = cal.compute_binned_calibration(trades, n_bins=5)

    assert res["total_evaluated"] == 10
    assert res["well_calibrated"] is True
    assert res["max_calibration_error_pts"] <= 5.0
    # Brier score: 7 * (0.7-1)^2 + 3 * (0.7-0)^2 = 7*0.09 + 3*0.49 = 0.63 + 1.47 = 2.10 / 10 = 0.21
    assert res["brier_score"] == pytest.approx(0.21, abs=0.01)


def test_calibration_detects_miscalibrated_model():
    # Modelo predice 80% de exito (POP 0.80), pero en la realidad solo gana el 40% (4 de 10)
    # Error = |0.40 - 0.80| = 40 puntos > 10 puntos tolerados por G3
    trades = [
        mock_trade(i, 20.0 if i <= 4 else -20.0, pop=0.80)
        for i in range(1, 11)
    ]
    res = cal.compute_binned_calibration(trades, n_bins=5)
    assert res["well_calibrated"] is False
    assert res["max_calibration_error_pts"] == pytest.approx(40.0, abs=1.0)


def test_empirical_alpha_estimation_adjusts_with_evidence():
    # Muy pocas operaciones -> preserva prior
    few = [mock_trade(1, 20.0)]
    assert cal.estimate_empirical_alpha(few, prior_alpha=0.25)["alpha_status"] == "insufficient_data"

    # Muestra suficiente con alto win rate (80% vs 50% neutral) -> alpha sube
    many_wins = [mock_trade(i, 20.0 if i <= 24 else -20.0) for i in range(1, 31)]
    est_high = cal.estimate_empirical_alpha(many_wins, prior_alpha=0.25)
    assert est_high["estimated_alpha"] > 0.25

    # Muestra con bajo win rate (30%) -> alpha baja
    many_losses = [mock_trade(i, 20.0 if i <= 9 else -20.0) for i in range(1, 31)]
    est_low = cal.estimate_empirical_alpha(many_losses, prior_alpha=0.25)
    assert est_low["estimated_alpha"] < 0.25


# ====================================================================== 3. Gate G3 Probe
def test_gate_g3_verdict_pending_when_insufficient_shadow_time_or_trades():
    # Solo 5 trades y 1 semana
    trades = [mock_trade(i, 20.0) for i in range(1, 6)]
    today = date(2026, 10, 20)
    start = date(2026, 10, 13)  # 1 semana
    eval_res = g3.evaluate_gate_g3(trades, EFF, shadow_start_date=start, now=datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc))

    assert eval_res["verdict"] == "PENDING"
    assert eval_res["all_passed"] is False
    c1 = next(c for c in eval_res["criteria"] if c["id"] == "C-1")
    assert c1["status"] == "PENDING"
    c2 = next(c for c in eval_res["criteria"] if c["id"] == "C-2")
    assert c2["status"] == "PENDING"


def test_gate_g3_verdict_no_go_when_metrics_fail():
    # 60 trades (cumple volumen) y 5 semanas (cumple duracion), pero PnL negativo persistente
    trades = [mock_trade(i, -15.0) for i in range(1, 65)]
    start = date(2026, 9, 1)
    today = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
    eval_res = g3.evaluate_gate_g3(trades, EFF, shadow_start_date=start, now=today)

    assert eval_res["verdict"] == "NO-GO"
    c3 = next(c for c in eval_res["criteria"] if c["id"] == "C-3")
    assert c3["status"] == "FAIL"


def test_gate_g3_verdict_go_when_all_five_criteria_met():
    # 60 trades, 5 semanas, PnL positivo (expectancy > 0), calibracion bien calibrada (<= 10 pts), DD controlado
    # 40 wins (+25), 20 losses (-15) -> Win rate 66%, POP 0.65 -> Calibracion error ~1 pt
    start = date(2026, 9, 1)
    today = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
    trades = [
        mock_trade(i, 25.0 if i % 3 != 0 else -15.0, pop=0.65, exit_dt=(start + timedelta(days=i // 2)).isoformat())
        for i in range(1, 61)
    ]
    eval_res = g3.evaluate_gate_g3(trades, EFF, shadow_start_date=start, now=today)

    assert eval_res["verdict"] == "GO"
    assert eval_res["all_passed"] is True
    for crit in eval_res["criteria"]:
        assert crit["status"] == "PASS"
