"""
Tests de Selección por Máximo Beneficio Potencial y Pipeline de Auto-Ejecución de Opciones.
Verifica:
1. Presupuesto dinámico para Mega-Caps / ETFs (evita rechazos por $350 rígido).
2. Cálculo de Potential Benefit Index y ranking prioritario del mayor beneficio neto.
3. Filtro de umbral mínimo de beneficio ($ USD) y valor esperado ($ USD).
4. Auto-ejecución de candidatas seleccionadas hacia opt_paper_trades y stocks_orders (TWS).
"""
import pytest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from app.options import settings_defaults as sd
from app.options.strategies import _qty
from app.options.score import compute_potential_benefit_metrics, rank_and_score_candidates
from app.options.portfolio_selector import select_portfolio
from app.options.paper_execution import execute_selected_candidate_to_trade


def test_megacap_dynamic_risk_sizing():
    """Mega-Caps y ETFs líderes permiten contratos unitarios de calidad de hasta $1000."""
    eff = sd.effective_settings({"max_risk_per_trade_usd": 800})
    
    # NVDA Call unitario a $467 -> debe retornar qty=1
    qty_nvda = _qty(467.0, eff, symbol="NVDA")
    assert qty_nvda >= 1
    
    # SPY Call unitario a $850 (dentro de tolerancia megacap <= 1000) -> debe retornar qty=1
    qty_spy = _qty(850.0, eff, symbol="SPY")
    assert qty_spy == 1
    
    # AAPL Spread a $720 -> debe retornar qty=1
    qty_aapl = _qty(720.0, eff, symbol="AAPL")
    assert qty_aapl == 1

    # Ticker penny ordinario a $850 (no es megacap) -> debe ser 0 porque supera el max_risk base de 800
    qty_penny = _qty(850.0, eff, symbol="XYZ")
    assert qty_penny == 0


def test_potential_benefit_metrics_comparison():
    """El Benefit Index de un líder de alta rentabilidad (SPY/NVDA) supera con creces a un ticker barato (AAL)."""
    eff = sd.default_settings()

    # Candidata A: Ticker barato de bajo beneficio (AAL Bear Put Spread)
    aal_cand = {
        "id": 1,
        "symbol": "AAL",
        "qty": 8,
        "entry_debit": 0.35,
        "max_loss_contract": 35.0,
        "max_loss_total": 280.0,
        "max_profit_contract": 65.0,
        "ev_view_net": 9.95,
        "score": 50.4,
    }
    met_aal = compute_potential_benefit_metrics(aal_cand, eff)

    # Candidata B: Mega-Cap de alto beneficio (NVDA Bull Call Spread)
    nvda_cand = {
        "id": 2,
        "symbol": "NVDA",
        "qty": 2,
        "entry_debit": 3.50,
        "max_loss_contract": 350.0,
        "max_loss_total": 700.0,
        "max_profit_contract": 650.0,
        "ev_view_net": 95.00,
        "score": 75.0,
    }
    met_nvda = compute_potential_benefit_metrics(nvda_cand, eff)

    # Verificaciones matemáticas
    assert met_nvda["pot_profit_total"] > met_aal["pot_profit_total"]
    assert met_nvda["ev_total_usd"] > met_aal["ev_total_usd"]
    assert met_nvda["benefit_index"] > met_aal["benefit_index"]


def test_portfolio_selector_chooses_maximum_benefit():
    """El selector de cartera DEBE marcar como 'selected' al activo de mayor beneficio potencial."""
    eff = sd.default_settings()
    eff["max_open_risk_usd"] = 2500
    eff["max_risk_per_trade_usd"] = 800
    eff["max_daily_selections"] = 1  # Solo 1 cupo para obligar a elegir al mejor

    candidates = [
        {
            "id": 101,
            "underlying_id": 125,
            "symbol": "AAL",
            "strategy_type": "bear_put_spread",
            "direction": "bearish",
            "qty": 4,
            "entry_debit": 0.35,
            "max_loss_contract": 35.0,
            "max_loss_total": 140.0,
            "max_profit_contract": 65.0,
            "ev_view_net": 9.95,
            "score": 52.0,
            "eligibility_status": "eligible",
        },
        {
            "id": 102,
            "underlying_id": 1,
            "symbol": "SPY",
            "strategy_type": "bull_call_spread",
            "direction": "bullish",
            "qty": 1,
            "entry_debit": 4.50,
            "max_loss_contract": 450.0,
            "max_loss_total": 450.0,
            "max_profit_contract": 550.0,
            "ev_view_net": 88.00,
            "score": 74.0,
            "eligibility_status": "eligible",
        }
    ]

    res = select_portfolio(candidates, [], eff)
    assert len(res.selected) == 1
    selected = res.selected[0]
    
    # SPY debe ser la seleccionada por tener mayor beneficio potencial ($550 vs $260) y mayor EV ($88 vs $39.80)
    assert selected["id"] == 102
    assert selected["symbol"] == "SPY"
    assert selected["potential_profit_total"] == 550.0


def test_minimum_profit_hurdle_rejects_micro_gains():
    """Candidatas con beneficios potenciales o EV triviales son excluidas de la selección."""
    eff = sd.default_settings()
    eff["min_potential_profit_usd"] = 50.0
    eff["min_ev_total_usd"] = 15.0

    micro_cand = [
        {
            "id": 201,
            "underlying_id": 999,
            "symbol": "TINY",
            "strategy_type": "bull_call_spread",
            "direction": "bullish",
            "qty": 1,
            "entry_debit": 0.15,
            "max_loss_contract": 15.0,
            "max_loss_total": 15.0,
            "max_profit_contract": 25.0,  # $25 < $50 umbral
            "ev_view_net": 5.0,           # $5 < $15 umbral
            "score": 68.0,
            "eligibility_status": "eligible",
        }
    ]

    res = select_portfolio(micro_cand, [], eff)
    assert len(res.selected) == 0
    assert len(res.skipped) == 1
    assert "inferior al umbral minimo" in res.skipped[0]["reason"]


def test_auto_execution_pipeline_dispatches_orders():
    """execute_selected_candidate_to_trade crea posición en opt_paper_trades y despacha a stocks_orders."""
    sb = MagicMock()
    
    # Simular que no hay posición previa abierta
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

    # Mock insert response
    mock_pos = {
        "id": 99,
        "symbol": "NVDA",
        "strategy_type": "bull_call_spread",
        "direction": "bullish",
        "qty": 1,
        "status": "open",
        "entry_debit": 3.50,
        "max_loss_total": 350.0,
        "max_profit_total": 650.0,
    }
    sb.table.return_value.insert.return_value.execute.return_value.data = [mock_pos]

    cand = {
        "id": 555,
        "underlying_id": 2,
        "symbol": "NVDA",
        "strategy_type": "bull_call_spread",
        "direction": "bullish",
        "qty": 1,
        "expiry": "2026-10-30",
        "legs": [
            {"strike": 140.0, "right": "C", "side": "buy", "bid": 4.10, "ask": 4.20, "market_data_type": "LIVE", "expiry": "2026-10-30"},
            {"strike": 145.0, "right": "C", "side": "sell", "bid": 1.35, "ask": 1.40, "market_data_type": "LIVE", "expiry": "2026-10-30"}
        ],
        "entry_debit": 2.85,
        "exec_overcost_pct": 2.5,
        "max_loss_contract": 300.0,
        "max_loss_total": 300.0,
        "max_profit_contract": 200.0,
        "eligibility_status": "selected",
    }
    und = {"id": 2, "symbol": "NVDA", "event_flags": []}
    eff = sd.default_settings()
    eff["allow_delayed_data"] = True

    pos = execute_selected_candidate_to_trade(sb, cand, eff, und=und)
    assert pos is not None
    assert pos["symbol"] == "NVDA"

    # Verificar que se llamó a stocks_orders para ambas piernas
    calls = [c[0][0] for c in sb.table.call_args_list]
    assert "opt_paper_trades" in calls
    assert "stocks_orders" in calls
