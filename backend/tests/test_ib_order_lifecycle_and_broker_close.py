"""
Unit tests for:
1. RVOL-guided Single-Order Adaptive Ladder / Chaser (`order_execution_plan.py`)
2. Broker-Confirmed Close (`broker_sync.request_broker_option_close`, `is_option_closing_pending`)
3. `IBBridgeWorker` working-order reprice, TTL cancel, orphan sweep, and SELL fill confirmation
4. Broker-First entry in `autonomous_options_dispatcher.py`
"""
import os
import sys
import time
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_entry_plan_scales_aggressiveness_by_rvol():
    from app.options.order_execution_plan import compute_option_entry_plan

    low = compute_option_entry_plan(bid=2.00, ask=2.40, mid=2.20, rvol=1.0)
    med = compute_option_entry_plan(bid=2.00, ask=2.40, mid=2.20, rvol=1.5)
    high = compute_option_entry_plan(bid=2.00, ask=2.40, mid=2.20, rvol=2.6)

    # Mid=2.20, Spread=0.40 -> low=2.30, med=2.40, high=2.40 (capped at Ask)
    assert low["limit_price"] == 2.30
    assert med["limit_price"] == 2.40
    assert high["limit_price"] == 2.40
    assert low["adaptive_priority"] == "Normal"
    assert high["adaptive_priority"] == "Urgent"
    assert high["ttl_sec"] < low["ttl_sec"]
    assert high["reprice_after_sec"] < low["reprice_after_sec"]


def test_reprice_limit_respects_chase_cap():
    from app.options.order_execution_plan import compute_reprice_limit

    step1 = compute_reprice_limit(current_lmt=2.30, max_chase_price=2.60, live_bid=2.35, live_ask=2.45, reprice_count=0)
    assert step1["action"] == "replace"
    assert step1["new_lmt"] == 2.45

    step2_nudge = compute_reprice_limit(current_lmt=2.45, max_chase_price=2.60, live_bid=2.40, live_ask=2.45, reprice_count=1)
    assert step2_nudge["action"] == "replace"
    assert step2_nudge["new_lmt"] == 2.46

    runaway = compute_reprice_limit(current_lmt=2.46, max_chase_price=2.60, live_bid=2.70, live_ask=2.85, reprice_count=1)
    assert runaway["action"] == "cancel_chase_exceeded"


def test_request_broker_option_close_keeps_open_while_held_in_tws():
    from app.options.broker_sync import request_broker_option_close, is_option_closing_pending

    pos = {
        "id": 77,
        "symbol": "SPY",
        "expiry": "2026-11-20",
        "strategy_type": "long_call",
        "qty": 2,
        "entry_fills": [{"strike": 600.0, "right": "C"}],
        "exit_plan": {},
    }

    mock_sb = MagicMock()
    opt_tbl = MagicMock()
    ord_tbl = MagicMock()
    ord_tbl.select.return_value.eq.return_value.eq.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = []

    def _table(name):
        if name == "stocks_orders":
            return ord_tbl
        if name == "opt_paper_trades":
            return opt_tbl
        return MagicMock()

    mock_sb.table.side_effect = _table

    portfolio_snapshot = {
        "SPY:OPT:20261120:600.0:C": {
            "sec_type": "OPT",
            "underlying": "SPY",
            "expiry": "20261120",
            "strike": 600.0,
            "right": "C",
            "shares": 2,
        }
    }

    with patch("app.options.broker_sync.load_broker_portfolio_snapshot", return_value=(portfolio_snapshot, 5.0)), \
         patch("app.options.broker_sync.is_option_held_in_broker", return_value=(True, 2)), \
         patch("app.stocks.stocks_order_executor.is_ib_bridge_alive", return_value=True):
        res = request_broker_option_close(
            sb=mock_sb,
            pos=pos,
            qty_to_close=2,
            exit_price_est=3.10,
            mapped_reason="take_profit",
            detailed_reason="TP_HIT",
        )

    assert res["status"] == "closing_pending"
    assert res["order_enqueued"] is True

    # Verificar que opt_paper_trades NO recibió status='closed', sino exit_plan['closing_pending']=True
    upd_payload = opt_tbl.update.call_args[0][0]
    assert "status" not in upd_payload
    assert upd_payload["exit_plan"]["closing_pending"] is True
    assert upd_payload["exit_plan"]["pending_exit_reason"] == "take_profit"

    pos_after = dict(pos, exit_plan=upd_payload["exit_plan"])
    assert is_option_closing_pending(mock_sb, pos_after) is True


def test_request_broker_option_close_returns_flat_when_fresh_tws_shows_zero():
    from app.options.broker_sync import request_broker_option_close

    pos = {
        "id": 78,
        "symbol": "QQQ",
        "expiry": "2026-11-20",
        "strategy_type": "long_put",
        "qty": 1,
        "entry_fills": [{"strike": 500.0, "right": "P"}],
        "exit_plan": {},
    }
    mock_sb = MagicMock()
    with patch("app.options.broker_sync.load_broker_portfolio_snapshot", return_value=({}, 4.0)), \
         patch("app.options.broker_sync.is_option_held_in_broker", return_value=(False, 0)), \
         patch("app.stocks.stocks_order_executor.is_ib_bridge_alive", return_value=True):
        res = request_broker_option_close(
            sb=mock_sb,
            pos=pos,
            qty_to_close=1,
            exit_price_est=2.50,
            mapped_reason="stop_loss",
            detailed_reason="SL_HIT",
        )
    assert res["status"] == "broker_already_flat"


def test_manage_working_orders_reprices_cancels_ttl_and_sweeps_orphans():
    from app.workers.ib_bridge_worker import IBBridgeWorker, WORKING_IB_ORDERS, PENDING_IB_ORDERS

    WORKING_IB_ORDERS.clear()
    PENDING_IB_ORDERS.clear()

    worker = IBBridgeWorker.__new__(IBBridgeWorker)
    worker.ib = MagicMock()
    worker.ib.connected = True
    worker.ib.get_contract_quote.return_value = {"bid": 2.40, "ask": 2.50}
    worker.ib.request_open_orders.return_value = {
        9001: {"order_id": 9001, "client_id": 26, "action": "BUY", "symbol": "NVDA", "sec_type": "OPT", "status": "Submitted"},
        9002: {"order_id": 9002, "client_id": 0, "action": "BUY", "symbol": "AAPL", "sec_type": "OPT", "status": "Submitted"},
    }

    # 1) Orden para re-price (lleva 25s, reprice_after=15s, ttl=60s)
    ib_ord_reprice = MagicMock(lmtPrice=2.30)
    contract_reprice = MagicMock(symbol="SPY")
    WORKING_IB_ORDERS[501] = {
        "order_ctx": {"id": "ord-501", "ticker": "SPY:OPT:20261120:600:C"},
        "contract": contract_reprice,
        "ib_ord": ib_ord_reprice,
        "quote_key": "SPY:OPT:20261120:600.0:C",
        "placed_at": time.time() - 25.0,
        "last_reprice_at": time.time() - 25.0,
        "reprice_count": 0,
        "max_chase_price": 2.70,
        "reprice_after_sec": 15.0,
        "ttl_sec": 60.0,
        "is_option": True,
        "direction": "buy",
    }

    # 2) Orden expirada por TTL (lleva 65s, ttl=60s)
    WORKING_IB_ORDERS[502] = {
        "order_ctx": {"id": "ord-502", "ticker": "TSLA:OPT:20261120:300:C"},
        "contract": MagicMock(symbol="TSLA"),
        "ib_ord": MagicMock(lmtPrice=4.10),
        "quote_key": "TSLA:OPT:20261120:300.0:C",
        "placed_at": time.time() - 65.0,
        "last_reprice_at": time.time() - 40.0,
        "reprice_count": 1,
        "max_chase_price": 4.40,
        "reprice_after_sec": 20.0,
        "ttl_sec": 60.0,
        "is_option": True,
        "direction": "buy",
    }
    PENDING_IB_ORDERS[502] = WORKING_IB_ORDERS[502]["order_ctx"]

    # Simular que huérfana 9001 ya fue vista hace 65s
    worker._orphan_first_seen = {9001: time.time() - 65.0}

    mock_sb = MagicMock()
    with patch("app.workers.ib_bridge_worker.get_supabase", return_value=mock_sb):
        worker.manage_working_orders(sweep_orphans=True)

    # Re-price ejecutado en 501
    assert ib_ord_reprice.lmtPrice == 2.50
    assert WORKING_IB_ORDERS[501]["reprice_count"] == 1
    worker.ib.placeOrder.assert_called_once_with(501, contract_reprice, ib_ord_reprice)

    # Cancelación por TTL en 502 y por huérfana API en 9001 (NO 9002 manual client_id=0)
    cancelled_ids = [c.args[0] for c in worker.ib.cancelOrder.call_args_list]
    assert 502 in cancelled_ids
    assert 9001 in cancelled_ids
    assert 9002 not in cancelled_ids
    assert 502 not in WORKING_IB_ORDERS

    WORKING_IB_ORDERS.clear()
    PENDING_IB_ORDERS.clear()


def test_on_ib_order_status_sell_fill_closes_pending_option():
    from app.workers.ib_bridge_worker import on_ib_order_status, PENDING_IB_ORDERS, WORKING_IB_ORDERS

    PENDING_IB_ORDERS.clear()
    WORKING_IB_ORDERS.clear()

    PENDING_IB_ORDERS[701] = {
        "id": "ord-sell-701",
        "ticker": "NVDA",
        "target_band": "OPT:20261120:150.0:C",
        "group_name": "OPTIONS_AUTONOMOUS",
        "direction": "sell",
        "shares": 2,
        "market_price": 5.00,
        "limit_price": 5.00,
    }

    open_row = {
        "id": 99,
        "symbol": "NVDA",
        "strategy_type": "long_call",
        "expiry": "2026-11-20",
        "qty": 2,
        "entry_debit": 4.00,
        "entry_total_invested": 800.0,
        "realized_pnl": 0.0,
        "status": "open",
        "entry_fills": [{"strike": 150.0, "right": "C"}],
        "exit_plan": {
            "closing_pending": True,
            "pending_exit_reason": "take_profit",
            "detailed_exit_reason": "TP_GAIN_25",
        },
    }

    mock_sb = MagicMock()
    opt_tbl = MagicMock()
    opt_tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [open_row]
    ord_tbl = MagicMock()
    jrn_tbl = MagicMock()

    def _table(name):
        if name == "opt_paper_trades":
            return opt_tbl
        if name == "stocks_orders":
            return ord_tbl
        if name == "trades_journal":
            return jrn_tbl
        return MagicMock()

    mock_sb.table.side_effect = _table

    with patch("app.workers.ib_bridge_worker.get_supabase", return_value=mock_sb), \
         patch("app.workers.ib_bridge_worker.send_telegram_alert"), \
         patch("app.workers.ib_bridge_worker.ACTIVE_BRIDGE", None):
        on_ib_order_status(701, {"status": "filled", "filled": 2, "avg_fill_price": 5.20})

    upd = opt_tbl.update.call_args[0][0]
    assert upd["status"] == "closed"
    assert upd["exit_credit"] == 5.20
    assert upd["exit_reason"] == "take_profit"
    assert upd["exit_plan"]["closing_pending"] is False
    assert upd["realized_pnl"] > 0
    assert jrn_tbl.insert.called
    assert 701 not in PENDING_IB_ORDERS


def test_autonomous_dispatcher_broker_first_and_rvol_pricing():
    from app.options.autonomous_options_dispatcher import dispatch_autonomous_option_trade

    mock_sb = MagicMock()
    inserted_tables = []

    def _table(name):
        t = MagicMock()
        t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        t.select.return_value.like.return_value.in_.return_value.execute.return_value.data = []

        def _insert(payload):
            inserted_tables.append((name, payload))
            m = MagicMock()
            m.execute.return_value.data = [{"id": "ord-rvol-1"}]
            return m

        t.insert.side_effect = _insert
        return t

    mock_sb.table.side_effect = _table

    mock_contract = MagicMock(
        symbol="SPY",
        right="C",
        strike=600.0,
        expiry=date(2026, 11, 20),
        bid=3.00,
        ask=3.40,
        mid=3.20,
        conid=111222,
        contract_id=111222,
        tranche_1_contracts=1,
    )

    cand = {"ticker": "SPY", "price": 600.0, "rvol": 2.5, "triggered_rule": "BULL_EXPANSION"}

    from datetime import datetime, timezone as _tz
    _det_now = datetime(2026, 11, 18, 15, 0, tzinfo=_tz.utc)
    with patch("app.options.autonomous_options_dispatcher.evaluate_structural_regime", return_value={"can_enter_call": True}), \
         patch("app.options.autonomous_options_dispatcher.is_ticker_in_options_cooldown", return_value=(False, "")), \
         patch("app.options.aduana_gap_runner_options.fetch_and_evaluate_options_gatekeeper", return_value={"approved": True}), \
         patch("app.options.autonomous_options_dispatcher.fetch_and_select_best_option_contract", return_value=(mock_contract, [])), \
         patch("app.core.circuit_breaker.can_open_new_trade", return_value=(True, "OK")), \
         patch("app.core.structural_regime_engine.evaluate_macro_daily_bias", return_value={"veto_calls": False, "veto_puts": False}), \
         patch("app.options.autonomous_options_dispatcher.send_telegram_alert"):
        res = dispatch_autonomous_option_trade(cand, direction="CALL", supabase=mock_sb, now_dt=_det_now)

    assert res["success"] is True
    assert res["price"] == 3.40  # RVOL=2.5 -> Mid + 0.75*spread = 3.50 capped at Ask 3.40
    # Principio Broker-First: solo inserta en stocks_orders, NO en opt_paper_trades
    table_names = [n for n, _ in inserted_tables]
    assert table_names == ["stocks_orders"]
    assert inserted_tables[0][1]["rvol"] == 2.5
