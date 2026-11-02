"""
Unit Tests for Radar Cuántico ETI & Ross Cameron Dual-Tier Integration
======================================================================
Valida:
1. Modelos de datos del contrato ETI (v2.3.0) y el Instructivo Táctico de 5 Pilares.
2. Motor TA Gate: Prioridad 1 (Ross Cameron) vs Opción 2 (Fallback Trigger Directo ETI).
3. Selector de Contratos en modo 0DTE_SCALP (vencimiento de hoy / ultra-cercano).
4. Inyección en /api/v1/options/opportunities con máxima prioridad (#1).
5. Ejecución Paper Trading y Feedback a ETI.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, date, timedelta

from app.options.eti_models import ETISignal, ETITacticalInstruction
from app.options.eti_storage import (
    save_eti_signal,
    get_active_eti_signals,
    get_eti_signal_by_id,
    seed_default_sample_signal,
    update_eti_signal_status
)
from app.options.eti_ta_gate import evaluate_eti_ta_gate
from app.options.opt_contract_picker import select_best_option_contract
from app.api.options import list_opportunities, simulate_entry


@pytest.fixture
def sample_meta_put_signal() -> ETISignal:
    now = datetime.now(timezone.utc)
    exp = (now + timedelta(hours=2)).isoformat()
    raw = {
        "signal_id": "test-eti-meta-put-001",
        "timestamp": now.isoformat(),
        "expires_at": exp,
        "cadence": "PRE_MARKET",
        "status": "ACTIVE",
        "symbol": "META",
        "asset_class": "OPTION_0DTE",
        "action": "BUY_TO_OPEN",
        "options_contract": {
            "contract_symbol": "META261102P00590000",
            "option_type": "PUT",
            "strike": 590.0,
            "expiration_date": now.strftime("%Y-%m-%d"),
            "dte": 0,
            "target_delta": -0.42,
            "max_bid_ask_spread_pct": 3.5,
            "estimated_contract_price": 2.75
        },
        "strategy": {
            "horizon": "SCALPING",
            "bias": "BEARISH",
            "playbook_rule": "META_GAMMA_CASCADE_PUT_0DTE",
            "expected_duration_minutes": 30
        },
        "causal_context": {
            "fde_regime": "DECELERATION",
            "fcg_confidence_pct": 91.5,
            "primary_source": "Yoel Sardiñas (FCG Calibración #14 - Short Gamma Cascade)",
            "catalyst_summary": "Subida de rendimientos de bonos a 10 años (4.93%) + Presiones regulatorias antimonopolio.",
            "catalyst_impact_score": -0.78,
            "greeks_thesis": "Gamma extrema en strikes $590-$595. Si el precio pierde $592.50, acelera la caída."
        },
        "technical_gate": {
            "trigger_type": "VWAP_REJECTION",
            "underlying_trigger_price": 592.50,
            "trigger_operator": "LESS_THAN_OR_EQUAL",
            "indicator_requirements": {
                "vwap_condition": "PRICE_BELOW_VWAP",
                "ema_fast_vs_slow": "FAST_BELOW_SLOW",
                "min_relative_volume": 1.35,
                "timeframe_confirmation": "2m"
            }
        },
        "risk_management": {
            "invalidation_underlying": 596.20,
            "stop_loss_contract_pct": -20.0,
            "take_profit_1_pct": 40.0,
            "take_profit_2_pct": 90.0,
            "runner_trailing_stop_pct": 20.0,
            "max_account_risk_pct": 2.5
        },
        "safety_guardrails": {
            "execution_allowed": True,
            "max_slippage_pct": 1.5,
            "circuit_breaker_active": False
        }
    }
    sig = ETISignal.model_validate(raw)
    sig.get_or_create_tactical_instruction()
    return sig


def test_eti_signal_data_contract_and_5_pillars(sample_meta_put_signal):
    """Verifica el cumplimiento estricto del contrato y los 5 pilares tácticos."""
    sig = sample_meta_put_signal
    assert sig.symbol == "META"
    assert sig.asset_class == "OPTION_0DTE"
    assert sig.strategy.horizon == "SCALPING"
    assert sig.options_contract.dte == 0
    assert sig.causal_context.fde_regime == "DECELERATION"

    # Verificar generación de los 5 pilares
    inst = sig.get_or_create_tactical_instruction()
    assert inst.escenario_activo == "META_GAMMA_CASCADE_PUT_0DTE"
    assert inst.trigger_activacion == 592.50
    assert inst.invalidacion_stop == 596.20
    assert "TP1: +40%" in inst.rango_objetivo
    assert "Yoel Sardiñas" in inst.racional_causal_forrester
    assert "Ross Cameron" in inst.prioridad_1_ross_cameron or "First Candle" in inst.prioridad_1_ross_cameron


def test_ta_gate_invalidation_by_stop_forrester(sample_meta_put_signal):
    """Verifica que el Stop de Invalidación Forrester descarte la señal si el precio supera el límite."""
    sig = sample_meta_put_signal

    # Crear barras sintéticas donde el precio está a $598.00 (> $596.20 invalidación)
    df_synthetic = pd.DataFrame({
        "close": [595.0, 596.0, 597.0, 598.0, 598.5],
        "open":  [594.0, 595.0, 596.5, 597.5, 598.0],
        "high":  [595.5, 596.5, 597.5, 598.8, 599.0],
        "low":   [593.5, 594.5, 595.5, 596.8, 597.5],
        "volume": [1000, 1200, 1100, 1500, 2000]
    })

    res = evaluate_eti_ta_gate(sig, df_2m=df_synthetic)
    assert res.is_invalidated is True
    assert res.is_triggered is False
    assert res.status_p2 == "INVALIDATED"
    assert "superó Stop Forrester" in res.reason


def test_ta_gate_option_2_direct_trigger_breakout(sample_meta_put_signal):
    """Verifica que la Opción 2 gatille cuando el precio perfora el nivel Trigger sin esperar a Ross Cameron."""
    sig = sample_meta_put_signal

    # Precio perfora $592.50 cayendo a $591.20, por debajo de VWAP ($594.00) con RVOL alto (2.0x)
    # pero sin patrón ordenado de micro-pullback de velas
    df_breakout = pd.DataFrame({
        "close": [595.0, 594.0, 593.0, 592.0, 591.20],
        "open":  [595.5, 594.5, 593.5, 592.8, 592.10],
        "high":  [596.0, 595.0, 594.0, 593.0, 592.30],
        "low":   [594.5, 593.5, 592.5, 591.5, 590.80],
        "volume": [500, 600, 700, 800, 1800] # Volumen creciente en la rotura
    })

    res = evaluate_eti_ta_gate(sig, df_2m=df_breakout)
    assert res.is_triggered is True
    assert res.selected_route == "OPTION_2_FALLBACK_ETI"
    assert res.status_p2 == "TRIGGERED"
    assert "Opción 2 Fallback" in res.reason


def test_ta_gate_priority_1_ross_cameron(sample_meta_put_signal):
    """Verifica que la Prioridad 1 (Ross Cameron) gatille tras rebote a EMA9/VWAP y First Candle New Low."""
    sig = sample_meta_put_signal

    # Secuencia Ross Cameron para PUT:
    # 1. Impulso bajista
    # 2. Rebote ordenado de 2 velas verdes hacia VWAP/EMA9
    # 3. Vela actual roja perfora el mínimo de la vela previa (First Candle New Low)
    df_ross = pd.DataFrame({
        "close": [593.0, 591.5, 592.2, 592.8, 591.0], # Vela -1 cerró en 592.8, vela actual cae a 591.0 perforando mínimo previo
        "open":  [594.0, 592.5, 591.6, 592.1, 592.7],
        "high":  [594.5, 593.0, 592.6, 593.2, 592.8],
        "low":   [592.8, 591.2, 591.5, 592.0, 590.5], # Min previo fue 592.0; min actual es 590.5
        "volume": [800, 1500, 600, 500, 2200]         # Rebote con volumen bajo (600, 500), ignición en el quiebre (2200)
    })

    res = evaluate_eti_ta_gate(sig, df_2m=df_ross)
    assert res.is_triggered is True
    assert res.selected_route == "PRIORITY_1_ROSS_CAMERON"
    assert res.status_p1 == "TRIGGERED"
    assert "Ross Cameron P1 PUT" in res.reason


def test_contract_picker_0dte_scalp_support():
    """Verifica que opt_contract_picker acepte contratos 0DTE y cercanos en modo 0DTE_SCALP."""
    today = date.today()
    mock_contracts = [
        # Contrato 0DTE (hoy)
        {
            "contract_id": 101,
            "conid": 101,
            "symbol": "META",
            "right": "P",
            "strike": 590.0,
            "expiry": today.isoformat(),
            "bid": 2.70,
            "ask": 2.80,
            "open_interest": 450,
            "volume": 200,
            "delta": -0.45
        },
        # Contrato de 15 DTE (habitual swing)
        {
            "contract_id": 102,
            "conid": 102,
            "symbol": "META",
            "right": "P",
            "strike": 590.0,
            "expiry": (today + timedelta(days=15)).isoformat(),
            "bid": 6.10,
            "ask": 6.30,
            "open_interest": 800,
            "volume": 350,
            "delta": -0.45
        }
    ]

    # En modo GAP_RUNNER (swing), el contrato 0DTE debe ser rechazado por DTE < 10
    selected_swing, rejections_swing = select_best_option_contract(
        contracts=mock_contracts,
        underlying_price=592.0,
        direction="PUT",
        selection_mode="GAP_RUNNER",
        now_date=today
    )
    assert selected_swing is not None
    assert selected_swing.dte == 15

    # En modo 0DTE_SCALP (Radar Cuántico ETI), debe aceptar y seleccionar el contrato 0DTE (dte=0)
    selected_0dte, rejections_0dte = select_best_option_contract(
        contracts=mock_contracts,
        underlying_price=592.0,
        direction="PUT",
        selection_mode="0DTE_SCALP",
        now_date=today
    )
    assert selected_0dte is not None
    assert selected_0dte.dte == 0
    assert selected_0dte.strike == 590.0
    assert selected_0dte.right == "P"


def test_opportunities_api_priority_ranking(sample_meta_put_signal):
    """Verifica que list_opportunities retorne la señal ETI con ALTA PRIORIDAD (Rank #1, Score > 95)."""
    # Guardar señal
    save_eti_signal(sample_meta_put_signal)

    res = list_opportunities()
    assert "items" in res
    assert "summary" in res
    assert res["summary"].get("total_eti_signals", 0) >= 1
    assert res["summary"].get("has_eti_signals") is True

    items = res["items"]
    assert len(items) >= 1

    top_item = items[0]
    assert top_item.get("is_eti_signal") is True
    assert top_item.get("symbol") == "META"
    assert top_item.get("score") >= 95.0
    assert top_item.get("rank_global") == 1
    assert "tactical_instruction" in top_item
    assert top_item["tactical_instruction"]["escenario_activo"] == "META_GAMMA_CASCADE_PUT_0DTE"


def test_simulate_entry_for_eti_signal(sample_meta_put_signal):
    """Verifica que simulate_entry procese la entrada para una candidata ETI y registre la ruta seleccionada."""
    save_eti_signal(sample_meta_put_signal)

    payload = {
        "candidate_id": f"eti-{sample_meta_put_signal.signal_id}",
        "route": "PRIORITY_1_ROSS_CAMERON"
    }

    res = simulate_entry(payload)
    assert res["ok"] is True
    assert res["route_used"] == "PRIORITY_1_ROSS_CAMERON"
    assert "META" in res["message"]
    assert res["position"]["symbol"] == "META"
    assert res["position"]["exit_plan"]["execution_route"] == "PRIORITY_1_ROSS_CAMERON"
