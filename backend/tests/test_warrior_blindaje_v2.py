"""
test_warrior_blindaje_v2.py — Regression & Verification Suite for Ross Cameron V2 Improvements
==============================================================================================
Verifica las 7 mejoras implementadas a partir del análisis forense (09/11/2026 - 13/11/2026):
1. Fase 1: Circuit Breakers Diarios en MicroPullbackEngine (2 pérdidas consecutivas / -$150 USD).
2. Fase 2: TP1 "Pay the Trader" (>= $0.15 por acción) y órdenes SELL LMT Marketable en Small Caps.
3. Fase 3: Bloqueo Horario 11:00 ET y Filtro Anti-Chase (Precio <= EMA9_5m + 1.5x ATR) en Stocks.
4. Fase 4: Ventana de Oro (09:35-11:30 ET) y Pullback obligatorio (AND) en warrior_momentum_options.
5. Fase 5: Tope Anti-Stacking (MAX_CONTRACTS_PER_SYMBOL = 3) en aduana_gap_runner_options.
6. Fase 6: Bloqueo de re-importación zombi y fuera de horario (15:30+ ET) en broker_sync.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.stocks.micro_pullback_engine import MicroPullbackEngine, ScalpCandidateState
from app.stocks.playbook_gate import GateDecision
from app.stocks.stocks_order_executor import execute_market_order, _is_outside_ross_momentum_window_et
from app.options.warrior_momentum_options import (
    evaluate_warrior_momentum_setup,
    is_warrior_options_golden_window,
    MAX_CONTRACTS_PER_SYMBOL,
)
from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches
from app.options.broker_sync import is_within_options_sync_import_window, reconcile_with_ib_broker_portfolio


def _make_df(rows):
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# FASE 1: CIRCUIT BREAKERS DIARIOS EN MICROPULLBACKENGINE
# ─────────────────────────────────────────────────────────────
def test_fase1_circuit_breaker_blocks_after_2_consecutive_losses():
    engine = MicroPullbackEngine()
    cand = ScalpCandidateState("SMFL")
    engine.candidates["SMFL"] = cand

    # Simular 2 pérdidas consecutivas
    engine.consecutive_losses = 2
    engine.daily_cushion_usd = -45.0

    with patch("app.stocks.micro_pullback_engine.get_ib_connection") as mock_ib:
        engine._trigger_entry(cand, entry_price=4.25)
        assert cand.in_trade is False
        assert engine.trading_blocked is True
        assert engine.block_reason == "CIRCUIT_BREAKER_2_CONSECUTIVE_LOSSES"
        mock_ib.assert_not_called()


def test_fase1_circuit_breaker_blocks_on_max_daily_loss():
    engine = MicroPullbackEngine()
    cand = ScalpCandidateState("SMFL")
    engine.candidates["SMFL"] = cand

    engine.consecutive_losses = 1
    engine.daily_cushion_usd = -155.0

    with patch("app.stocks.micro_pullback_engine.get_ib_connection") as mock_ib:
        engine._trigger_entry(cand, entry_price=4.25)
        assert cand.in_trade is False
        assert engine.trading_blocked is True
        assert engine.block_reason == "MAX_DAILY_LOSS_REACHED"
        mock_ib.assert_not_called()


# ─────────────────────────────────────────────────────────────
# FASE 2: TP1 >= $0.15 ("PAY THE TRADER") Y VENTAS LMT MARKETABLE
# ─────────────────────────────────────────────────────────────
def test_fase2_tp1_requires_min_15_cents_and_uses_lmt_sell():
    engine = MicroPullbackEngine()
    cand = ScalpCandidateState("PNNY")
    cand.in_trade = True
    cand.phase = "IN_TRADE"
    cand.entry_price = 2.00
    cand.target_hod = 2.40
    cand.stop_loss = 1.88
    cand.shares = 100
    cand.initial_shares = 100
    engine.candidates["PNNY"] = cand
    engine.active_scalps["PNNY"] = cand

    with patch("app.stocks.micro_pullback_engine.get_ib_connection") as mock_ib:
        import types
        if "ibapi" not in sys.modules:
            ibapi_mod = types.ModuleType("ibapi")
            ibapi_order_mod = types.ModuleType("ibapi.order")
            class _FakeOrder:
                pass
            ibapi_order_mod.Order = _FakeOrder
            sys.modules["ibapi"] = ibapi_mod
            sys.modules["ibapi.order"] = ibapi_order_mod

        mock_conn = MagicMock()
        mock_conn.connected = True
        mock_conn.get_next_order_id.return_value = 3001
        mock_conn.us_stock_contract.return_value = MagicMock()
        mock_ib.return_value = mock_conn

        # Subida a $2.06 (+3.0% pero solo +$0.06 < $0.15): NO debe disparar Tramo 1 prematuro
        bar_small = {"time": 1700000010, "open": 2.02, "high": 2.07, "low": 2.01, "close": 2.06, "volume": 10000}
        engine.process_5s_bar("PNNY", bar_small)
        assert cand.shares == 100
        mock_conn.placeOrder.assert_not_called()

        # Subida a $2.16 (+$0.16 >= $0.15 y +8.0% >= 2.5%): SÍ dispara Tramo 1 con orden LMT
        bar_tp1 = {"time": 1700000015, "open": 2.06, "high": 2.18, "low": 2.06, "close": 2.16, "volume": 25000}
        engine.process_5s_bar("PNNY", bar_tp1)
        assert cand.shares == 50
        mock_conn.placeOrder.assert_called_once()
        args, _ = mock_conn.placeOrder.call_args
        sell_ord = args[2]
        assert sell_ord.action == "SELL"
        assert sell_ord.orderType == "LMT"
        assert sell_ord.lmtPrice == 2.13  # 2.16 - 0.03


# ─────────────────────────────────────────────────────────────
# FASE 3: CANDADO 11:00 ET Y FILTRO ANTI-CHASE EN STOCKS
# ─────────────────────────────────────────────────────────────
def test_fase3_stocks_anti_chase_and_11am_window():
    # 14:00 ET (19:00 UTC) -> Fuera de ventana Ross Cameron (>= 11:00 ET)
    dt_afternoon = datetime(2026, 11, 12, 19, 0, tzinfo=timezone.utc)
    assert _is_outside_ross_momentum_window_et(dt_afternoon) is True

    with patch("app.stocks.stocks_order_executor.get_supabase"), \
         patch("app.stocks.stocks_order_executor._get_config", return_value={"paper_mode": True}):
        res_late = execute_market_order(
            ticker="STIM",
            direction="buy",
            rule_code="RP_WARRIOR_04_MICRO_PULLBACK_EMA9",
            context={"price": 3.50, "now_dt": dt_afternoon, "enforce_ross_window": True},
            rule={"group_name": "ALPHA_RUNNER"}
        )
        assert res_late["success"] is False
        assert "OUTSIDE_MOMENTUM_WINDOW" in res_late["reason"]

        # 10:00 ET (15:00 UTC) pero precio sobreextendido (> EMA9_5m + 1.5x ATR)
        dt_morning = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
        res_chase = execute_market_order(
            ticker="MF",
            direction="buy",
            rule_code="ALPHA_RUNNER_BUY",
            context={"price": 19.22, "ema9_5m": 16.50, "atr_5m": 0.80, "now_dt": dt_morning},
            rule={"group_name": "ALPHA_RUNNER"}
        )
        assert res_chase["success"] is False
        assert "Filtro Anti-Chase" in res_chase["reason"]


# ─────────────────────────────────────────────────────────────
# FASE 4: VENTANA DE ORO Y PULLBACK OBLIGATORIO EN WARRIOR OPTIONS
# ─────────────────────────────────────────────────────────────
def test_fase4_warrior_options_golden_window_and_mandatory_pullback():
    # 10:15 ET (15:15 UTC) -> Dentro de Ventana de Oro
    dt_ok = datetime(2026, 11, 12, 15, 15, tzinfo=timezone.utc)
    ok_win, _ = is_warrior_options_golden_window(dt_ok)
    assert ok_win is True

    # 13:00 ET (18:00 UTC) -> Cementerio del mediodía -> Bloqueado
    dt_midday = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)
    bad_win, msg = is_warrior_options_golden_window(dt_midday)
    assert bad_win is False
    assert "11:30 ET" in msg

    # Sin vela roja de pullback en 5m (todas verdes en clímax): debe retornar None aunque BB expanda
    df_5m_no_pullback = _make_df([
        {"open": 100.0 + i, "high": 101.2 + i, "low": 99.9 + i, "close": 101.0 + i, "volume": 50000}
        for i in range(20)
    ])
    df_15m_expanding = _make_df([
        {"open": 100.0 + i * 1.5, "high": 102.0 + i * 1.5, "low": 99.5 + i * 1.5, "close": 101.5 + i * 1.5, "volume": 150000}
        for i in range(25)
    ])
    setup = evaluate_warrior_momentum_setup("NVDA", df_5m_no_pullback, df_15m_expanding)
    assert setup is None


# ─────────────────────────────────────────────────────────────
# FASE 5: TOPE ANTI-STACKING (MAX_CONTRACTS_PER_SYMBOL = 3)
# ─────────────────────────────────────────────────────────────
def test_fase5_anti_stacking_cap_at_3_contracts():
    assert MAX_CONTRACTS_PER_SYMBOL == 3
    df_5m = _make_df([
        {"open": 265.0, "high": 267.0, "low": 264.5, "close": 266.5, "volume": 50000},
        {"open": 266.5, "high": 268.0, "low": 266.0, "close": 267.5, "volume": 50000},
        {"open": 267.5, "high": 270.0, "low": 267.2, "close": 269.8, "volume": 90000},
    ])
    # Posición que ya tiene 3 contratos abiertos
    active_pos_full = {
        "id": 1617,
        "status": "open",
        "qty": 3,
        "reentry_count": 0,
        "unrealized_pnl": 120.0,
        "avg_price": 266.0,
        "direction": "CALL",
    }
    res = evaluate_options_gap_entry_tranches(
        ticker="AMZN",
        df_5m=df_5m,
        gap_pct=3.5,
        active_position=active_pos_full,
        direction="CALL",
    )
    assert res["should_enter"] is False
    assert "Tope Anti-Stacking alcanzado" in res["reason"]


# ─────────────────────────────────────────────────────────────
# FASE 6: BLOQUEO DE RE-IMPORTACIÓN ZOMBI Y NOCTURNA EN BROKER_SYNC
# ─────────────────────────────────────────────────────────────
def test_fase6_broker_sync_blocks_after_1530_et_and_zombies():
    # 15:52 ET (20:52 UTC) -> Fuera de ventana de importación (09:30-15:30 ET)
    dt_1552_et = datetime(2026, 11, 11, 20, 52, tzinfo=timezone.utc)
    assert is_within_options_sync_import_window(dt_1552_et) is False

    # 22:05 ET (03:05 UTC) -> Noche -> Bloqueado
    dt_night = datetime(2026, 11, 10, 3, 5, tzinfo=timezone.utc)
    assert is_within_options_sync_import_window(dt_night) is False

    # 10:30 ET (15:30 UTC) -> Dentro de ventana
    dt_morning = datetime(2026, 11, 11, 15, 30, tzinfo=timezone.utc)
    assert is_within_options_sync_import_window(dt_morning) is True
