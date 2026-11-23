"""
Suite de regresión forense para Blindaje Operativo V3 (Fases 1 a 7).
Ejecución 100% determinista y offline (sin llamadas a TWS/Supabase/yfinance reales).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def _make_table_chain(rows_by_call=None):
    """Genera un query builder compatible con Supabase/MagicMock."""
    chain = MagicMock()
    for method in (
        "select", "insert", "update", "upsert", "delete",
        "eq", "neq", "in_", "gte", "lte", "gt", "lt", "order", "limit",
    ):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = SimpleNamespace(data=rows_by_call if rows_by_call is not None else [])
    return chain


def _make_candle_df(closes, opens=None, highs=None, lows=None, volumes=None):
    n = len(closes)
    opens = opens if opens is not None else list(closes)
    highs = highs if highs is not None else [max(o, c) + 0.05 for o, c in zip(opens, closes)]
    lows = lows if lows is not None else [min(o, c) - 0.05 for o, c in zip(opens, closes)]
    volumes = volumes if volumes is not None else [10000.0] * n
    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 1: Post-Bollinger 15m + EOD Hard-Exit + Sync Import/Liquidate Window
# ═══════════════════════════════════════════════════════════════════════════════

def test_bb15m_exhaustion_call_and_long_stock():
    from app.core.bb15m_exhaustion import evaluate_bb15m_post_breakout_exhaustion

    closes = [100.0 + (0.05 if i % 2 == 0 else -0.05) for i in range(20)]
    opens = [100.0] * 20
    highs = [c + 0.08 for c in closes]
    lows = [c - 0.08 for c in closes]

    # Vela 21: ruptura alcista fuerte sobre BB_Upper -> strong_push mantiene
    df_breakout = _make_candle_df(
        closes=closes + [104.5],
        opens=opens + [100.2],
        highs=highs + [104.6],
        lows=lows + [100.1],
    )
    res_break = evaluate_bb15m_post_breakout_exhaustion(
        df_breakout, is_bullish=True, state={}, current_price=104.5, position_age_minutes=15.0, asset_type="option"
    )
    assert res_break["should_exit"] is False
    assert res_break["state"]["bb15m_upper_breakout_seen"] is True

    # Vela 22: lateralización / giro descendente tras ruptura BB_Upper -> salida 100%
    df_stall = _make_candle_df(
        closes=closes + [104.5, 104.2],
        opens=opens + [100.2, 104.5],
        highs=highs + [104.6, 104.55],
        lows=lows + [100.1, 104.0],
    )
    res_exit_opt = evaluate_bb15m_post_breakout_exhaustion(
        df_stall, is_bullish=True, state=res_break["state"], current_price=104.2, position_age_minutes=20.0, asset_type="option"
    )
    assert res_exit_opt["should_exit"] is True
    assert res_exit_opt["exit_ratio"] == 1.0
    assert res_exit_opt["rule_code"] == "OPT_BB15M_EXHAUSTION_EXIT"

    res_exit_stk = evaluate_bb15m_post_breakout_exhaustion(
        df_stall, is_bullish=True, state=res_break["state"], current_price=104.2, position_age_minutes=20.0, asset_type="stock"
    )
    assert res_exit_stk["should_exit"] is True
    assert res_exit_stk["rule_code"] == "STK_BB15M_EXHAUSTION_EXIT"

    # Posición muy joven (< 5 min) no debe disparar todavía
    res_young = evaluate_bb15m_post_breakout_exhaustion(
        df_stall, is_bullish=True, state=res_break["state"], current_price=104.2, position_age_minutes=2.5, asset_type="option"
    )
    assert res_young["should_exit"] is False


def test_bb15m_exhaustion_put_and_short_stock():
    from app.core.bb15m_exhaustion import evaluate_bb15m_post_breakout_exhaustion

    closes = [100.0 + (0.05 if i % 2 == 0 else -0.05) for i in range(20)]
    opens = [100.0] * 20
    highs = [c + 0.08 for c in closes]
    lows = [c - 0.08 for c in closes]

    # Ruptura bajista fuerte bajo BB_Lower -> strong_drop mantiene
    df_drop = _make_candle_df(
        closes=closes + [95.5],
        opens=opens + [99.8],
        highs=highs + [99.9],
        lows=lows + [95.4],
    )
    res_drop = evaluate_bb15m_post_breakout_exhaustion(
        df_drop, is_bullish=False, state={}, current_price=95.5, position_age_minutes=12.0, asset_type="option"
    )
    assert res_drop["should_exit"] is False
    assert res_drop["state"]["bb15m_lower_breakout_seen"] is True

    # Vela 22: rebote/lateralización tras romper BB_Lower -> salida 100% inmediata
    df_bounce = _make_candle_df(
        closes=closes + [95.5, 95.8],
        opens=opens + [99.8, 95.5],
        highs=highs + [99.9, 96.0],
        lows=lows + [95.4, 95.45],
    )
    res_exit_put = evaluate_bb15m_post_breakout_exhaustion(
        df_bounce, is_bullish=False, state=res_drop["state"], current_price=95.8, position_age_minutes=18.0, asset_type="option"
    )
    assert res_exit_put["should_exit"] is True
    assert res_exit_put["exit_ratio"] == 1.0
    assert res_exit_put["rule_code"] == "OPT_BB15M_EXHAUSTION_EXIT"


def test_eod_hard_exit_dte_le_7_and_late_import_flag():
    from app.options.exit_engine import should_exit_by_time
    from app.options.settings_defaults import effective_settings

    eff = effective_settings({})
    # Miércoles 2026-11-18 15:46 ET -> 20:46 UTC (EST = UTC-5)
    now_eod = datetime(2026, 11, 18, 20, 46, tzinfo=timezone.utc)
    pos_4dte = {
        "symbol": "QQQ",
        "expiry": "2026-11-22",  # DTE = 4 <= 7
        "exit_plan": {},
    }
    should_exit, reason = should_exit_by_time(pos_4dte, now_eod, eff)
    assert should_exit is True
    assert "DTE=4d" in (reason or "")

    # Contrato > 7 DTE (ej. DTE=14) no cierra por EOD de intradía/semanal a las 15:46
    pos_14dte = {"symbol": "SPY", "expiry": "2026-12-02", "exit_plan": {}}
    should_exit_far, _ = should_exit_by_time(pos_14dte, now_eod, eff)
    assert should_exit_far is False

    # Flag late_import_force_close debe forzar cierre a cualquier hora
    now_morning = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)  # 10:00 ET
    pos_late = {"symbol": "NVDA", "expiry": "2026-12-18", "exit_plan": {"late_import_force_close": True}}
    should_exit_late, reason_late = should_exit_by_time(pos_late, now_morning, eff)
    assert should_exit_late is True
    assert "late_import_force_close" in (reason_late or "")


def test_broker_sync_windows_and_late_liquidation_dedup():
    from app.options.broker_sync import (
        is_within_options_sync_import_window,
        is_within_options_late_liquidate_window,
        enqueue_late_option_liquidation,
    )

    t_1000_et = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)
    t_1525_et = datetime(2026, 11, 18, 20, 25, tzinfo=timezone.utc)
    t_1545_et = datetime(2026, 11, 18, 20, 45, tzinfo=timezone.utc)
    t_1605_et = datetime(2026, 11, 18, 21, 5, tzinfo=timezone.utc)
    t_2200_et = datetime(2026, 11, 19, 3, 0, tzinfo=timezone.utc)

    assert is_within_options_sync_import_window(t_1000_et) is True
    assert is_within_options_sync_import_window(t_1545_et) is False
    assert is_within_options_sync_import_window(t_2200_et) is False

    assert is_within_options_late_liquidate_window(t_1545_et) is True
    assert is_within_options_late_liquidate_window(t_1525_et) is False
    assert is_within_options_late_liquidate_window(t_1605_et) is False

    # Sin orden activa -> despacha SELL MKT
    orders_tbl = _make_table_chain([])
    sb = MagicMock()
    sb.table.return_value = orders_tbl
    assert enqueue_late_option_liquidation(sb, "QQQ", "2026-11-23", 610.0, "P", 1, 8.20, now_dt=t_1545_et) is True
    orders_tbl.insert.assert_called_once()
    inserted_payload = orders_tbl.insert.call_args[0][0]
    assert inserted_payload["direction"] == "sell"
    assert inserted_payload["order_type"] == "market"

    # Con orden activa dentro de 45s -> deduplica
    recent_tbl = _make_table_chain([{"id": 99, "created_at": (t_1545_et - timedelta(seconds=15)).isoformat(), "status": "pending"}])
    sb2 = MagicMock()
    sb2.table.return_value = recent_tbl
    assert enqueue_late_option_liquidation(sb2, "QQQ", "2026-11-23", 610.0, "P", 1, 8.20, now_dt=t_1545_et) is False


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 2: Límites desde Settings (5% Stocks / $800 Opciones) + Cierre paper_execution
# ═══════════════════════════════════════════════════════════════════════════════

def test_stocks_settings_5_percent_and_zero_share_rejection():
    from app.stocks import stocks_order_executor as soe

    tc_tbl = _make_table_chain([{"capital_stocks_spot": 5000.0}])
    sc_tbl = _make_table_chain([
        {"key": "max_pct_per_trade", "value": "5"},
        {"key": "pct_per_operation", "value": "10"},
        {"key": "enforce_ross_window", "value": "true"},
        {"key": "trading_mode", "value": "paper"},
    ])
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tc_tbl if name == "trading_config" else sc_tbl

    with patch.object(soe, "get_supabase", return_value=mock_sb):
        cfg = soe._get_config()

    assert cfg["total_capital"] == 5000.0
    assert cfg["max_pct_per_trade"] == 0.05
    assert cfg["paper_mode"] is True

    # 5% de $5,000 = $250. Si 1 acción cuesta $300 -> debe rechazar (0 shares), no redondear a 1
    assert soe._calculate_shares(5000.0, 0.05, 300.0) == 0
    assert soe._calculate_shares(5000.0, 0.05, 50.0) == 5


def test_options_settings_800_cap_and_no_megacap_bypass():
    from app.options.settings_defaults import effective_settings, get_effective_max_risk_per_trade_usd
    from app.options import options_aduana as oa

    assert get_effective_max_risk_per_trade_usd(None, None) == 800.0

    os_tbl = _make_table_chain([{"max_risk_per_trade_usd": 800.0}])
    sb = MagicMock()
    sb.table.return_value = os_tbl
    assert get_effective_max_risk_per_trade_usd(sb, {}) == 800.0

    eff = effective_settings({})
    ctx = oa.static_context(1, [], underlying={"id": 1, "symbol": "QQQ"})
    ctx.check_window = False
    ctx.check_quote_age = False
    cand = {
        "id": 101,
        "underlying_id": 1,
        "symbol": "QQQ",
        "strategy_type": "long_call",
        "direction": "bullish",
        "expiry": "2026-11-23",
        "qty": 1,
        "max_loss_contract": 950.0,
        "max_loss_total": 950.0,  # > $800, antes pasaba por megacap $1,500
        "legs": [{"side": "buy", "right": "C", "strike": 600.0, "bid": 9.40, "ask": 9.50, "market_data_type": "LIVE"}],
    }
    res = oa.validate_entry(cand, ctx, eff)
    assert res.approved is False
    o3 = next(r for r in res.rules if r.rule == "O-3")
    assert o3.ok is False


def test_paper_execution_enforces_golden_window_800_cap_and_expires_at():
    from app.options.paper_execution import execute_selected_candidate_to_trade
    from app.options.settings_defaults import effective_settings

    eff = effective_settings({})
    t_outside = datetime(2026, 11, 18, 16, 40, tzinfo=timezone.utc)  # 11:40 ET (fuera de 09:35-11:30)
    t_golden = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)    # 10:00 ET (dentro de Ventana de Oro)

    cand_base = {
        "id": 77,
        "underlying_id": 1,
        "symbol": "NVDA",
        "strategy_type": "long_put",
        "direction": "bearish",
        "expiry": "2026-11-23",
        "qty": 5,
        "max_loss_contract": 250.0,
        "max_loss_total": 750.0,
        "legs": [{"conid": 999, "side": "buy", "right": "P", "strike": 140.0, "bid": 2.40, "ask": 2.50, "market_data_type": "LIVE"}],
    }

    sb_out = MagicMock()
    with patch("app.options.paper_execution.is_market_open", return_value=(True, "OPEN")):
        assert execute_selected_candidate_to_trade(sb_out, cand_base, eff, und={"id": 1, "symbol": "NVDA"}, now_dt=t_outside) is None

    hb_payload = json.dumps({"connected": True, "timestamp": datetime.now(timezone.utc).isoformat()})

    # 1 contrato cuesta ~$945 (> $800) -> rechazado
    cand_expensive = dict(
        cand_base,
        qty=1,
        max_loss_contract=950.0,
        max_loss_total=950.0,
        legs=[{"conid": 999, "side": "buy", "right": "P", "strike": 140.0, "bid": 9.40, "ask": 9.50, "market_data_type": "LIVE"}],
    )
    tables_exp = {
        "opt_paper_trades": _make_table_chain([]),
        "stocks_orders": _make_table_chain([]),
        "opt_settings": _make_table_chain([{"max_risk_per_trade_usd": 800.0}]),
        "stocks_config": _make_table_chain([{"value": hb_payload}]),
    }
    sb_exp = MagicMock()
    sb_exp.table.side_effect = lambda n: tables_exp.get(n, _make_table_chain([]))

    with patch("app.options.paper_execution.is_market_open", return_value=(True, "OPEN")), \
         patch("app.core.circuit_breaker.can_open_new_trade", return_value=(True, "OK")), \
         patch("app.options.exit_engine.is_ticker_in_options_cooldown", return_value=(False, "")), \
         patch("app.options.options_aduana.validate_entry", return_value=MagicMock(approved=True)):
        assert execute_selected_candidate_to_trade(sb_exp, cand_expensive, eff, und={"id": 1, "symbol": "NVDA", "event_flags": []}, now_dt=t_golden) is None

    # Candidato válido con qty=5 requested -> limitado a MAX_CONTRACTS_PER_SYMBOL=3 y tope $800, con expires_at (~90s)
    orders_tbl = _make_table_chain([])
    tables_ok = {
        "opt_paper_trades": _make_table_chain([]),
        "stocks_orders": orders_tbl,
        "opt_settings": _make_table_chain([{"max_risk_per_trade_usd": 800.0}]),
        "stocks_config": _make_table_chain([{"value": hb_payload}]),
    }
    sb_ok = MagicMock()
    sb_ok.table.side_effect = lambda n: tables_ok.get(n, _make_table_chain([]))

    with patch("app.options.paper_execution.is_market_open", return_value=(True, "OPEN")), \
         patch("app.core.circuit_breaker.can_open_new_trade", return_value=(True, "OK")), \
         patch("app.options.exit_engine.is_ticker_in_options_cooldown", return_value=(False, "")), \
         patch("app.options.options_aduana.validate_entry", return_value=MagicMock(approved=True)):
        res_ok = execute_selected_candidate_to_trade(sb_ok, cand_base, eff, und={"id": 1, "symbol": "NVDA", "event_flags": []}, now_dt=t_golden)

    assert res_ok is not None
    assert res_ok["qty"] <= 3
    orders_tbl.insert.assert_called_once()
    order_ins = orders_tbl.insert.call_args[0][0]
    assert order_ins["shares"] <= 3
    assert order_ins["expires_at"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 3: Reglas de TP (>= +5% obligatorio) y frontera 0DTE
# ═══════════════════════════════════════════════════════════════════════════════

def test_tp_climax_and_partial_require_min_5_percent_profit():
    from app.options.aduana_gap_runner_options import evaluate_options_gap_aduana_exit

    closes_1h = [100.0 + i * 1.2 for i in range(25)]
    df_1h = _make_candle_df(closes=closes_1h, opens=[c - 0.5 for c in closes_1h])
    closes_5m = [125.0 + i * 0.4 for i in range(25)]
    df_5m = _make_candle_df(closes=closes_5m, opens=[c - 0.2 for c in closes_5m])
    closes_15m = [120.0 + i * 0.5 for i in range(25)]
    df_15m = _make_candle_df(closes=closes_15m, opens=[c - 0.2 for c in closes_15m])

    pos = {
        "symbol": "PLTR",
        "strategy_type": "long_call",
        "direction": "bullish",
        "entry_debit": 10.0,
        "entry_total_invested": 1000.0,
        "qty": 1,
        "tp_block1_executed": False,
        "exit_plan": {},
    }

    # PnL = -10% (9.0) y +2% (10.2): NO debe disparar Climax ni Partial
    for prem in (9.0, 10.2):
        r = evaluate_options_gap_aduana_exit(
            pos,
            current_underlying_price=135.0,
            current_option_premium=prem,
            df_5m=df_5m,
            df_15m=df_15m,
            df_1h=df_1h,
            position_age_minutes=20.0,
        )
        assert r.get("rule_code") not in ("OPT_GAP_TP_CLIMAX", "OPT_GAP_TP_UPPER6_PARTIAL", "OPT_GAP_TP_LOWER6_PARTIAL")

    # PnL = +10% (11.0): SÍ puede disparar OPT_GAP_TP_CLIMAX con RSI 1H >= 85
    r_win = evaluate_options_gap_aduana_exit(
        pos,
        current_underlying_price=135.0,
        current_option_premium=11.0,
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        position_age_minutes=20.0,
    )
    assert r_win["should_exit"] is True
    assert r_win["rule_code"] == "OPT_GAP_TP_CLIMAX"


def test_zero_dte_guard_does_not_classify_7_dte_as_0dte():
    now_et = datetime(2026, 11, 18, 10, 0)
    exp_7dte = datetime.strptime("2026-11-25", "%Y-%m-%d").date()
    dte_days_v = (exp_7dte - now_et.date()).days
    assert dte_days_v == 7
    assert (dte_days_v <= 1) is False


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 4: TWS Tick Snapping, Safe Cancel Retention y Stuck Watchdog
# ═══════════════════════════════════════════════════════════════════════════════

def test_snap_option_tick_and_ib_safe_cancel_retention_and_watchdog():
    from app.options.order_execution_plan import snap_option_tick
    from app.workers import ib_bridge_worker as ibw

    assert snap_option_tick(3.52, "nearest") == 3.50
    assert snap_option_tick(3.53, "nearest") == 3.55
    assert snap_option_tick(3.52, "ceil") == 3.55
    assert snap_option_tick(3.52, "floor") == 3.50
    assert snap_option_tick(1.234, "nearest") == 1.23

    orig_pending = dict(ibw.PENDING_IB_ORDERS)
    orig_working = dict(ibw.WORKING_IB_ORDERS)
    try:
        ibw.PENDING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.clear()

        now_ts = 1_700_000_000.0
        mock_ib = MagicMock()
        worker = ibw.IBBridgeWorker.__new__(ibw.IBBridgeWorker)
        worker.ib = mock_ib
        worker._orphan_first_seen = {}

        ibw.PENDING_IB_ORDERS[502] = {"order_id": 7002, "symbol": "QQQ", "direction": "buy"}
        ibw.WORKING_IB_ORDERS[502] = {
            "order_ctx": {"id": 7002, "ticker": "QQQ"},
            "order_id": 7002,
            "ticker": "QQQ",
            "direction": "buy",
            "placed_at": now_ts - 120.0,
            "ttl_sec": 60.0,
            "is_option": True,
        }

        orders_tbl = _make_table_chain([])
        sb = MagicMock()
        sb.table.return_value = orders_tbl

        with patch.object(ibw, "get_supabase", return_value=sb), \
             patch.object(ibw.time, "time", return_value=now_ts):
            worker.manage_working_orders(sweep_orphans=False)

        mock_ib.cancelOrder.assert_called_once_with(502)
        assert 502 not in ibw.WORKING_IB_ORDERS
        # CRÍTICO: debe retenerse en PENDING_IB_ORDERS con _cancel_requested_at hasta callback TWS
        assert 502 in ibw.PENDING_IB_ORDERS
        assert ibw.PENDING_IB_ORDERS[502]["_cancel_requested_at"] == now_ts
        orders_tbl.update.assert_not_called()

        # Watchdog processing > 180s: libera ID 888 pero respeta ID 7002 (en PENDING) y ID 889 (< 180s)
        ref_now = datetime(2026, 11, 18, 16, 0, 0, tzinfo=timezone.utc)
        proc_rows = [
            {"id": 888, "ticker": "SPY", "direction": "buy", "status": "processing", "updated_at": (ref_now - timedelta(seconds=210)).isoformat()},
            {"id": 7002, "ticker": "QQQ", "direction": "buy", "status": "processing", "updated_at": (ref_now - timedelta(seconds=250)).isoformat()},
            {"id": 889, "ticker": "NVDA", "direction": "buy", "status": "processing", "updated_at": (ref_now - timedelta(seconds=60)).isoformat()},
        ]
        wd_tbl = _make_table_chain(proc_rows)
        sb_wd = MagicMock()
        sb_wd.table.return_value = wd_tbl

        with patch.object(ibw, "get_supabase", return_value=sb_wd):
            cleaned = worker.cleanup_stuck_processing_orders(max_age_sec=180.0, now_dt=ref_now)

        assert cleaned == [888]
    finally:
        ibw.PENDING_IB_ORDERS.clear()
        ibw.PENDING_IB_ORDERS.update(orig_pending)
        ibw.WORKING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.update(orig_working)


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 5 & 6: parse_iso_utc, SHORT TP Manager, trades_journal Dedup y sell_ord
# ═══════════════════════════════════════════════════════════════════════════════

def test_parse_iso_utc_and_short_tp_manager_direction():
    from app.core.time_utils import parse_iso_utc
    from app.stocks import stocks_tp_manager as tp_mgr

    dt5 = parse_iso_utc("2026-11-18T16:12:41.77588+00:00")
    assert dt5 == datetime(2026, 11, 18, 16, 12, 41, 775880, tzinfo=timezone.utc)
    dt1 = parse_iso_utc("2026-11-18T16:12:41.1Z")
    assert dt1 == datetime(2026, 11, 18, 16, 12, 41, 100000, tzinfo=timezone.utc)
    assert parse_iso_utc("") is None
    assert parse_iso_utc(None) is None
    assert parse_iso_utc("not-a-timestamp") is None

    # SHORT stock -> orden de cierre BUY, no SELL
    orders_tbl = _make_table_chain([])
    pos_tbl = _make_table_chain([])
    sb = MagicMock()
    sb.table.side_effect = lambda name: orders_tbl if name == "stocks_orders" else pos_tbl

    short_pos = {
        "id": 42,
        "ticker": "QQQ",
        "direction": "short",
        "group_name": "IB_SYNC_AUTO",
        "entry_price": 500.0,
        "shares_remaining": 100,
    }
    with patch("app.stocks.stocks_order_executor.is_ib_bridge_alive", return_value=True):
        res = asyncio.run(tp_mgr.execute_partial_sell("QQQ", short_pos, 1, 100, 495.0, "CLOSE_SHORT", supabase=sb))

    assert res["success"] is True
    orders_tbl.insert.assert_called_once()
    ins_ord = orders_tbl.insert.call_args[0][0]
    assert ins_ord["direction"] == "buy"
    assert ins_ord["shares"] == 100


def test_reconcile_trades_journal_dedup_and_sell_ord_temporal_filter():
    from app.workers import ib_bridge_worker as ibw

    worker = ibw.IBBridgeWorker.__new__(ibw.IBBridgeWorker)
    now_dt = datetime.now(timezone.utc)
    recent_close_iso = (now_dt - timedelta(seconds=30)).isoformat()
    entry_dt = now_dt - timedelta(minutes=10)
    stale_sell_iso = (entry_dt - timedelta(hours=24)).isoformat()

    mock_ib = MagicMock()
    mock_ib.connected = True
    mock_ib._positions_sync_ok = True
    mock_ib._prices = {}
    mock_ib.request_broker_positions.return_value = {}
    worker.ib = mock_ib

    stocks_pos_tbl = _make_table_chain([{
        "id": 10,
        "ticker": "AAPL",
        "direction": "long",
        "status": "open",
        "shares": 10,
        "shares_remaining": 10,
        "avg_price": 200.0,
        "current_price": 205.0,
        "first_buy_at": (now_dt - timedelta(minutes=15)).isoformat(),
        "updated_at": (now_dt - timedelta(minutes=15)).isoformat(),
    }])
    tj_tbl = _make_table_chain([{
        "id": 501,
        "ticker": "AAPL",
        "shares": 10,
        "exit_price": 205.0,
        "exit_date": recent_close_iso,
    }])

    opt_tbl = _make_table_chain([{
        "id": 301,
        "symbol": "NVDA",
        "strategy_type": "long_put",
        "direction": "bearish",
        "status": "open",
        "qty": 1,
        "expiry": "2026-11-23",
        "entry_time": entry_dt.isoformat(),
        "entry_debit": 3.00,
        "entry_total_invested": 300.0,
        "entry_costs": 0.70,
        "last_mark_price": 3.50,
        "model_version": "v1.0-tws-sync",
        "entry_fills": [{"strike": 140.0, "right": "P"}],
    }])

    # Query-aware mock para stocks_orders: devuelve [] en active/pending y stale fill en status='filled' sell
    class _OrdersRouter:
        def __init__(self):
            self._filters = {}
            self._in_vals = ()

        def select(self, *_a, **_kw):
            self._filters = {}
            self._in_vals = ()
            return self

        def eq(self, k, v):
            self._filters[k] = v
            return self

        def in_(self, k, vals):
            if k == "status":
                self._in_vals = tuple(vals)
            return self

        def gte(self, *_a, **_kw):
            return self

        def order(self, *_a, **_kw):
            return self

        def limit(self, *_a, **_kw):
            return self

        def execute(self):
            if self._in_vals:
                return SimpleNamespace(data=[])
            if self._filters.get("ticker") == "NVDA" and self._filters.get("direction") == "sell" and self._filters.get("status") == "filled":
                return SimpleNamespace(data=[{"filled_price": 9.99, "filled_at": stale_sell_iso}])
            if self._filters.get("direction") == "buy" and self._filters.get("status") == "filled":
                return SimpleNamespace(data=[{"id": 1}])
            return SimpleNamespace(data=[])

    orders_router = _OrdersRouter()

    def _tbl(name):
        if name == "stocks_positions":
            return stocks_pos_tbl
        if name == "trades_journal":
            return tj_tbl
        if name == "opt_paper_trades":
            return opt_tbl
        if name == "stocks_orders":
            return orders_router
        return _make_table_chain([])

    sb = MagicMock()
    sb.table.side_effect = _tbl

    with patch.object(ibw, "get_supabase", return_value=sb), \
         patch("app.options.broker_sync.is_within_options_sync_import_window", return_value=True), \
         patch("app.options.broker_sync.is_within_options_late_liquidate_window", return_value=False), \
         patch("app.options.broker_sync.get_in_flight_option_sell_keys", return_value=set()):
        worker.reconcile_broker_portfolio()

    # AAPL se cierra pero trades_journal ya tiene registro idéntico dentro de 120s -> NO inserta duplicado
    stocks_pos_tbl.update.assert_called()
    tj_tbl.insert.assert_not_called()

    # NVDA se cierra sin usar filled_price=9.99 porque filled_at < entry_time
    opt_tbl.update.assert_called()
    upd_payload = opt_tbl.update.call_args[0][0]
    assert upd_payload["exit_credit"] != 9.99


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 7: Veto Macro Diario SPY/QQQ 1D y Disyuntor (Circuit Breaker)
# ═══════════════════════════════════════════════════════════════════════════════

def test_macro_daily_veto_and_circuit_breaker():
    from app.core.structural_regime_engine import evaluate_macro_daily_bias
    from app.core import circuit_breaker as cb

    # SPY y QQQ ambos con EMA3 < EMA9 y Price < VWAP -> Veto CALLs activo
    bear_res = evaluate_macro_daily_bias(
        spy_metrics={"ema3": 580.0, "ema9": 588.0},
        qqq_metrics={"ema3": 495.0, "ema9": 505.0},
        spy_price=578.0,
        spy_vwap=582.0,
        qqq_price=492.0,
        qqq_vwap=498.0,
    )
    assert bear_res["veto_calls"] is True
    assert bear_res["veto_swing_longs"] is True

    # Solo alcista -> sin veto
    bull_res = evaluate_macro_daily_bias(
        spy_metrics={"ema3": 592.0, "ema9": 588.0},
        qqq_metrics={"ema3": 508.0, "ema9": 505.0},
        spy_price=594.0,
        spy_vwap=590.0,
        qqq_price=510.0,
        qqq_vwap=506.0,
    )
    assert bull_res["veto_calls"] is False

    # Stateful Supabase mock para Circuit Breaker: 3 pérdidas / -$420 <= -$400 dispara disyuntor
    kv_store = {}

    class _CbTable:
        def __init__(self, tbl_name):
            self.tbl_name = tbl_name
            self._key_filter = None

        def select(self, *_a, **_kw):
            self._key_filter = None
            return self

        def eq(self, k, v):
            if k == "key":
                self._key_filter = v
            return self

        def limit(self, *_a, **_kw):
            return self

        def upsert(self, payload, **_kw):
            self._pending_upsert = payload
            return self

        def execute(self):
            if hasattr(self, "_pending_upsert"):
                p = self._pending_upsert
                del self._pending_upsert
                if isinstance(p, dict) and p.get("key"):
                    kv_store[p["key"]] = p["value"]
                return SimpleNamespace(data=[p])
            if self.tbl_name == "stocks_config" and self._key_filter == "circuit_breaker_state":
                val = kv_store.get("circuit_breaker_state")
                return SimpleNamespace(data=[{"value": val}] if val is not None else [])
            return SimpleNamespace(data=[])

    sb_cb = MagicMock()
    sb_cb.table.side_effect = lambda name: _CbTable(name)

    with patch.object(cb, "get_supabase", return_value=sb_cb, create=True):
        cb.record_trade_completion("NVDA", -150.0, sb=sb_cb)
        cb.record_trade_completion("PLTR", -150.0, sb=sb_cb)
        cb.record_trade_completion("QQQ", -120.0, sb=sb_cb)
        can_open, reason = cb.can_open_new_trade("AMD", sb=sb_cb)
    assert can_open is False
    assert reason
