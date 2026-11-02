"""
Tests for Live ETI System Connectivity & Real-time Signal Sync
Target: https://eti-zeta-one.vercel.app
"""

import asyncio
import pytest
from app.options.eti_signal_consumer import check_eti_connection, sync_signals_from_live_eti
from app.options.eti_storage import get_active_eti_signals
from app.options.eti_ta_gate import evaluate_eti_ta_gate


def test_eti_live_service_connectivity():
    """Valida que el servicio en https://eti-zeta-one.vercel.app responda HTTP 200 y detecte los componentes."""
    res = asyncio.run(check_eti_connection())
    assert res["connected"] is True
    assert res["status_code"] == 200
    assert res["latency_ms"] < 6000
    assert res["eti_service_detected"] is True
    assert res["robot_dispatch_active"] is True
    assert len(res["detected_symbols"]) >= 3


def test_eti_live_signal_synchronization():
    """Sincroniza en tiempo real las señales de la Matriz de Apertura Robot eTrade Dispatcher."""
    sync_res = asyncio.run(sync_signals_from_live_eti())
    assert sync_res["ok"] is True
    assert sync_res["ingested_count"] >= 3
    assert any("meta" in s for s in sync_res["signals"])

    active_signals = get_active_eti_signals()
    assert len(active_signals) >= 1
    
    meta_sig = next((s for s in active_signals if s.symbol == "META"), None)
    assert meta_sig is not None
    assert meta_sig.tactical_instruction is not None
    assert any(w in meta_sig.tactical_instruction.escenario_activo.upper() for w in ("BEARISH", "PUT", "GAMMA"))
    assert meta_sig.technical_gate.underlying_trigger_price > 0
    assert meta_sig.risk_management.invalidation_underlying > 0

    # Evaluar TA Gate para META
    gate_eval = evaluate_eti_ta_gate(meta_sig)
    assert gate_eval.current_price > 0
    assert gate_eval.status_p1 in ("WAITING_PULLBACK", "PULLBACK_FORMED", "TRIGGERED", "NOT_MET")
    assert gate_eval.status_p2 in ("MONITORING_PRICE", "TRIGGERED", "INVALIDATED")
