"""
test_eti_options_blindaje.py — Verification Suite for ETI Options Strategy Fixes
=================================================================================
Valida las 6 correcciones del flujo de compra/venta de opciones provenientes de ETI:
1. Prioridad 1 (Ross Cameron) exige RVOL >= min_rvol y proximidad al trigger de ETI.
2. Bloqueo de señales si Safety Guardrails (O-13 / Circuit Breaker) están inhabilitados.
3. Selector real de contrato (0DTE_SCALP) en eti_autonomous_dispatcher (cero strikes .2 o $2.50 fijos).
4. Bloqueo fuera de Ventana de Oro (09:35-11:30 ET) para 0DTE/PRE_MARKET y Guardarraíl O-13.
5. Mapeo de invalidation_underlying -> stop_loss_underlying y stop_loss_contract_pct (-20%) en exit_engine.
6. Eliminación de siembra automática de señal demo en get_active_eti_signals().
"""

import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.options.eti_models import ETISignal
from app.options.eti_ta_gate import evaluate_eti_ta_gate
from app.options.eti_autonomous_dispatcher import run_eti_autonomous_options_cycle
from app.options.opt_contract_picker import SelectedContract
from app.options.exit_engine import evaluate_technical_rules_and_stops
from app.options import eti_storage


def _make_signal(
    symbol="META",
    bias="BEARISH",
    option_type="PUT",
    trigger=592.50,
    invalidation=596.20,
    execution_allowed=True,
    catalyst_summary="Short Gamma Cascade",
):
    now = datetime.now(timezone.utc)
    exp = (now + timedelta(hours=4)).isoformat()
    return ETISignal.model_validate({
        "signal_id": f"test-eti-{symbol.lower()}-001",
        "timestamp": now.isoformat(),
        "expires_at": exp,
        "cadence": "PRE_MARKET",
        "status": "ACTIVE",
        "symbol": symbol,
        "asset_class": "OPTION_0DTE",
        "action": "BUY_TO_OPEN",
        "options_contract": {
            "contract_symbol": f"{symbol}261115{option_type[0]}00590000",
            "option_type": option_type,
            "strike": 590.0,
            "expiration_date": now.strftime("%Y-%m-%d"),
            "dte": 0,
            "target_delta": -0.42 if option_type == "PUT" else 0.42,
            "max_bid_ask_spread_pct": 3.5,
            "estimated_contract_price": 2.50,
        },
        "strategy": {
            "horizon": "SCALPING",
            "bias": bias,
            "playbook_rule": "META_GAMMA_CASCADE",
            "expected_duration_minutes": 30,
        },
        "causal_context": {
            "fde_regime": "DECELERATION",
            "fcg_confidence_pct": 90.0,
            "primary_source": "Yoel Sardiñas",
            "catalyst_summary": catalyst_summary,
            "catalyst_impact_score": -0.8 if bias == "BEARISH" else 0.8,
            "greeks_thesis": "Gamma cascade",
        },
        "technical_gate": {
            "trigger_type": "VWAP_REJECTION",
            "underlying_trigger_price": trigger,
            "trigger_operator": "LESS_THAN_OR_EQUAL" if option_type == "PUT" else "GREATER_THAN_OR_EQUAL",
            "indicator_requirements": {
                "vwap_condition": "PRICE_BELOW_VWAP" if option_type == "PUT" else "PRICE_ABOVE_VWAP",
                "ema_fast_vs_slow": "FAST_BELOW_SLOW" if option_type == "PUT" else "FAST_ABOVE_SLOW",
                "min_relative_volume": 1.35,
                "timeframe_confirmation": "2m",
            },
        },
        "risk_management": {
            "invalidation_underlying": invalidation,
            "stop_loss_contract_pct": -20.0,
            "take_profit_1_pct": 40.0,
            "take_profit_2_pct": 90.0,
            "runner_trailing_stop_pct": 20.0,
            "max_account_risk_pct": 2.5,
        },
        "safety_guardrails": {
            "execution_allowed": execution_allowed,
            "max_slippage_pct": 1.5,
            "circuit_breaker_active": False,
        },
    })


def test_eti_ta_gate_p1_requires_rvol_and_trigger_proximity():
    sig = _make_signal(trigger=592.50, invalidation=596.20)

    # 1. Patrón de velas Ross Cameron PUT válido, pero RVOL seco (volumen 300 vs promedio ~1000 -> 0.3x < 1.35x)
    df_low_vol = pd.DataFrame({
        "close": [593.0, 591.5, 592.2, 592.8, 591.0],
        "open":  [594.0, 592.5, 591.6, 592.1, 592.7],
        "high":  [594.5, 593.0, 592.6, 593.2, 592.8],
        "low":   [592.8, 591.2, 591.5, 592.0, 590.5],
        "volume": [1000, 1500, 1000, 1000, 300],
    })
    res_low_vol = evaluate_eti_ta_gate(sig, df_2m=df_low_vol)
    assert res_low_vol.is_triggered is False

    # 2. Volumen alto y patrón de velas, pero Spot en $595.50 demasiado lejos del trigger $592.50 (> +0.3%)
    df_far_trigger = pd.DataFrame({
        "close": [596.0, 595.0, 595.5, 596.0, 595.2],
        "open":  [596.5, 595.8, 595.1, 595.6, 595.9],
        "high":  [596.8, 596.0, 595.8, 596.1, 596.0],
        "low":   [595.5, 594.8, 594.9, 595.4, 595.0],
        "volume": [800, 1000, 600, 500, 2500],
    })
    res_far = evaluate_eti_ta_gate(sig, df_2m=df_far_trigger)
    assert res_far.is_triggered is False


def test_eti_ta_gate_blocks_safety_guardrails():
    sig_blocked = _make_signal(
        symbol="NVDA",
        bias="BULLISH",
        option_type="CALL",
        trigger=140.0,
        invalidation=138.0,
        execution_allowed=False,
    )
    df_ok = pd.DataFrame({
        "close": [139.0, 140.0, 139.5, 139.3, 140.5],
        "open":  [138.8, 139.2, 139.9, 139.6, 139.4],
        "high":  [139.2, 140.1, 140.0, 139.7, 140.8],
        "low":   [138.7, 139.0, 139.2, 139.1, 139.3],
        "volume": [500, 1000, 400, 400, 2000],
    })
    res = evaluate_eti_ta_gate(sig_blocked, df_2m=df_ok)
    assert res.is_triggered is False
    assert res.is_invalidated is True
    assert "Safety Guardrails" in res.reason


def test_eti_dispatcher_uses_real_contract_picker_and_skips_if_none():
    sig = _make_signal()
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []

    gate_triggered = MagicMock(
        is_triggered=True,
        selected_route="PRIORITY_1_ROSS_CAMERON",
        current_price=591.20,
        current_vwap=593.00,
        current_rvol=2.1,
        reason="Ross Cameron P1 PUT",
        status_p1="TRIGGERED",
    )

    # Caso A: No hay contrato líquido real -> NO debe insertar nada en stocks_orders
    with patch("app.options.eti_autonomous_dispatcher.is_options_market_open", return_value=(True, "OPEN")), \
         patch("app.options.eti_autonomous_dispatcher.get_active_eti_signals", return_value=[sig]), \
         patch("app.options.eti_autonomous_dispatcher.is_warrior_options_golden_window", return_value=(True, "OK")), \
         patch("app.options.eti_autonomous_dispatcher.evaluate_eti_ta_gate", return_value=gate_triggered), \
         patch("app.options.eti_autonomous_dispatcher.fetch_and_select_best_option_contract", return_value=(None, ["Spread wide"])):
        res_none = asyncio.run(run_eti_autonomous_options_cycle(supabase=mock_sb, config={"max_open_risk_usd": 5000.0}))
        assert res_none["executed"] == 0
        mock_sb.table("stocks_orders").insert.assert_not_called()

    # Caso B: Contrato real seleccionado -> usa strike real, precio ask real y tope de 3 contratos
    real_contract = SelectedContract(
        contract_id=9001,
        conid=9001,
        symbol="META",
        right="P",
        strike=590.0,
        expiry=date.today(),
        dte=0,
        bid=3.10,
        ask=3.20,
        mid=3.15,
        spread_pct=3.17,
        delta=-0.48,
        open_interest=1200,
        volume=650,
        cost_per_contract=315.0,
        target_total_contracts=5,
        tranche_1_contracts=5,  # excede 3 -> debe caparse a 3
        tranche_2_contracts=0,
        tranche_3_contracts=0,
        tranche_model="SINGLE",
        score=95.0,
    )

    with patch("app.options.eti_autonomous_dispatcher.is_options_market_open", return_value=(True, "OPEN")), \
         patch("app.options.eti_autonomous_dispatcher.get_active_eti_signals", return_value=[sig]), \
         patch("app.options.eti_autonomous_dispatcher.is_warrior_options_golden_window", return_value=(True, "OK")), \
         patch("app.options.eti_autonomous_dispatcher.evaluate_eti_ta_gate", return_value=gate_triggered), \
         patch("app.options.eti_autonomous_dispatcher.fetch_and_select_best_option_contract", return_value=(real_contract, [])), \
         patch("app.options.eti_autonomous_dispatcher.update_eti_signal_status"), \
         patch("app.options.eti_autonomous_dispatcher.send_signal_feedback_to_eti"):
        res_ok = asyncio.run(run_eti_autonomous_options_cycle(supabase=mock_sb, config={"max_open_risk_usd": 5000.0}))
        assert res_ok["executed"] == 1
        inserted_payload = mock_sb.table("stocks_orders").insert.call_args[0][0]
        assert inserted_payload["shares"] == 3  # Capado a MAX_CONTRACTS_PER_SYMBOL = 3
        assert inserted_payload["limit_price"] == 3.23  # 3.20 * 1.01
        assert ":590.0:P" in inserted_payload["target_band"]


def test_eti_dispatcher_respects_golden_window_and_o13():
    sig_call_o13 = _make_signal(
        symbol="NVDA",
        bias="BULLISH",
        option_type="CALL",
        trigger=140.0,
        invalidation=138.0,
        catalyst_summary="[O-13: ALLOW_PUTS_ONLY · FDE: DECELERATION] Test",
    )
    sig_put = _make_signal()

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []

    with patch("app.options.eti_autonomous_dispatcher.is_options_market_open", return_value=(True, "OPEN")), \
         patch("app.options.eti_autonomous_dispatcher.get_active_eti_signals", return_value=[sig_call_o13, sig_put]), \
         patch("app.options.eti_autonomous_dispatcher.is_warrior_options_golden_window", return_value=(False, "13:00 ET fuera de ventana")), \
         patch("app.options.eti_autonomous_dispatcher.evaluate_eti_ta_gate") as mock_gate:
        res = asyncio.run(run_eti_autonomous_options_cycle(supabase=mock_sb, config={"max_open_risk_usd": 5000.0}))
        assert res["executed"] == 0
        # Ni CALL (O-13) ni PUT (fuera de ventana) deben llegar al evaluador
        mock_gate.assert_not_called()


def test_eti_exit_engine_maps_invalidation_and_20pct_stop():
    now_dt = datetime.now(timezone.utc)
    # 1. Stop Forrester (invalidation_underlying = 596.20 para PUT)
    pos_forrester = {
        "symbol": "META",
        "strategy_type": "long_put",
        "direction": "bearish",
        "qty": 1,
        "entry_time": (now_dt - timedelta(minutes=8)).isoformat(),
        "unrealized_pnl_pct": -10.0,
        "exit_plan": {
            "invalidation_underlying": 596.20,
            "stop_loss_contract_pct": -20.0,
        },
    }
    tech_forrester = {
        "valid": True,
        "symbol": "META",
        "current_price": 596.50,  # Supera invalidación 596.20
        "ema9_15m": 594.0,
        "prev_ema9_15m": 594.0,
        "atr_15m": 1.0,
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos_forrester, tech_forrester, now_dt)
    assert should_exit is True
    assert reason == "sl_underlying_pierced"

    # 2. Stop de prima ETI (-20.0%) debe cortar antes del -30% genérico
    pos_prem = {
        "symbol": "META",
        "strategy_type": "long_put",
        "direction": "bearish",
        "qty": 1,
        "entry_time": (now_dt - timedelta(minutes=3)).isoformat(),
        "unrealized_pnl_pct": -21.0,
        "exit_plan": {
            "invalidation_underlying": 598.00,
            "stop_loss_contract_pct": -20.0,
        },
    }
    tech_ok = {
        "valid": True,
        "symbol": "META",
        "current_price": 593.00,
        "ema9_15m": 594.0,
        "prev_ema9_15m": 594.0,
        "atr_15m": 1.0,
    }
    should_exit_p, reason_p, info_p = evaluate_technical_rules_and_stops(pos_prem, tech_ok, now_dt)
    assert should_exit_p is True
    assert reason_p == "stop_loss"
    assert "-20.0%" in info_p["detail"]


def test_eti_storage_no_auto_seed_when_empty():
    with patch.object(eti_storage, "load_signals_from_disk", return_value=[]), \
         patch.object(eti_storage, "seed_default_sample_signal") as mock_seed:
        res = eti_storage.get_active_eti_signals()
        assert res == []
        mock_seed.assert_not_called()
