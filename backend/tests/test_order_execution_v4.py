"""
Suite de regresión para Blindaje de Ejecución de Órdenes V4 (Fases 1–4).
100% offline y determinista.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _make_chain(data=None):
    c = MagicMock()
    for m in ("select", "insert", "update", "upsert", "delete", "eq", "neq", "in_", "gte", "order", "limit"):
        getattr(c, m).return_value = c
    c.execute.return_value = SimpleNamespace(data=data if data is not None else [])
    return c


class _DummyIBOrder:
    pass


def _ibapi_sys_modules():
    mod_order = SimpleNamespace(Order=_DummyIBOrder)
    mod_root = SimpleNamespace(order=mod_order)
    return {"ibapi": mod_root, "ibapi.order": mod_order}


def test_ib_error_callback_marks_order_and_releases_locks():
    from app.data.ib_provider import IBConnection
    from app.workers import ib_bridge_worker as ibw

    orig_pending = dict(ibw.PENDING_IB_ORDERS)
    orig_working = dict(ibw.WORKING_IB_ORDERS)
    orig_active = ibw.ACTIVE_BRIDGE
    try:
        ibw.PENDING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.clear()

        conn = IBConnection.__new__(IBConnection)
        conn._errors = []
        conn._error_callback = None
        conn.set_error_callback(ibw.on_ib_order_error)

        bridge = ibw.IBBridgeWorker.__new__(ibw.IBBridgeWorker)
        bridge._in_flight_sells = {"NVDA": 50}
        ibw.ACTIVE_BRIDGE = bridge

        # Caso 1: Stock SELL rechazado con Error 201 -> failed + libera _in_flight_sells
        ibw.PENDING_IB_ORDERS[901] = {
            "id": "ord-stk-901",
            "ticker": "NVDA",
            "direction": "sell",
            "shares": 50,
            "group_name": "IB_PAPER",
        }
        ibw.WORKING_IB_ORDERS[901] = {"order_ctx": ibw.PENDING_IB_ORDERS[901]}

        # Caso 2: Option SELL rechazado con Error 202 -> cancelled + limpia closing_pending + fallback sin cancel_reason
        ibw.PENDING_IB_ORDERS[902] = {
            "id": "ord-opt-902",
            "ticker": "SPY",
            "target_band": "OPT:20261127:690.0:P",
            "direction": "sell",
            "shares": 1,
            "group_name": "OPTIONS_AUTONOMOUS",
        }
        ibw.WORKING_IB_ORDERS[902] = {"order_ctx": ibw.PENDING_IB_ORDERS[902]}

        updated_payloads = []
        opt_tbl = _make_chain([{
            "id": 77,
            "symbol": "SPY",
            "expiry": "2026-11-27",
            "entry_fills": [{"strike": 690.0, "right": "P"}],
            "exit_plan": {"closing_pending": True},
        }])

        class _OrdTbl:
            def update(self, payload):
                updated_payloads.append(payload)
                self._payload = payload
                return self

            def eq(self, *_a):
                return self

            def in_(self, *_a):
                return self

            def execute(self):
                if "cancel_reason" in self._payload:
                    raise RuntimeError("column cancel_reason does not exist")
                return SimpleNamespace(data=[])

        sb = MagicMock()
        sb.table.side_effect = lambda name: opt_tbl if name == "opt_paper_trades" else _OrdTbl()

        with patch.object(ibw, "get_supabase", return_value=sb):
            conn.error(901, 201, "Order rejected")
            conn.error(902, 202, "Order Canceled")

        assert bridge._in_flight_sells["NVDA"] == 0
        assert 901 not in ibw.PENDING_IB_ORDERS and 901 not in ibw.WORKING_IB_ORDERS
        assert 902 not in ibw.PENDING_IB_ORDERS and 902 not in ibw.WORKING_IB_ORDERS
        assert any(p.get("cancel_reason") == "IB_ERROR_201" for p in updated_payloads)
        assert any(p.get("status") == "failed" and "cancel_reason" not in p for p in updated_payloads)
        assert any(p.get("status") == "cancelled" and "cancel_reason" not in p for p in updated_payloads)
        opt_upd = opt_tbl.update.call_args[0][0]
        assert opt_upd["exit_plan"]["closing_pending"] is False
    finally:
        ibw.PENDING_IB_ORDERS.clear()
        ibw.PENDING_IB_ORDERS.update(orig_pending)
        ibw.WORKING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.update(orig_working)
        ibw.ACTIVE_BRIDGE = orig_active


def test_request_broker_positions_restores_on_timeout_and_sell_shield_uses_return():
    from app.data.ib_provider import IBConnection
    from app.workers import ib_bridge_worker as ibw

    conn = IBConnection.__new__(IBConnection)
    conn._positions_lock = threading.Lock()
    conn._last_valid_positions = {"SPY": {"shares": 40.0, "sec_type": "STK"}}
    conn._positions = {}
    conn._positions_event = MagicMock()
    conn._positions_event.wait.return_value = False  # Simula timeout positionEnd
    conn.reqMarketDataType = MagicMock()
    conn._ensure_account_updates = MagicMock()
    conn.reqPositions = MagicMock()
    conn.cancelPositions = MagicMock()

    res = conn.request_broker_positions(timeout=0.05)
    assert res == {"SPY": {"shares": 40.0, "sec_type": "STK"}}
    assert conn._positions == {"SPY": {"shares": 40.0, "sec_type": "STK"}}

    # Ahora probar que IBBridgeWorker.process_pending_orders usa el retorno del método incluso si self.ib._positions = {}
    orig_pending = dict(ibw.PENDING_IB_ORDERS)
    orig_working = dict(ibw.WORKING_IB_ORDERS)
    try:
        ibw.PENDING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.clear()

        worker = ibw.IBBridgeWorker.__new__(ibw.IBBridgeWorker)
        worker._reconcile_requested = False
        mock_ib = MagicMock()
        mock_ib.connected = True
        mock_ib._positions = {}  # Vacío en atributo interno, pero método retorna la posición real
        mock_ib.request_broker_positions.return_value = {
            "NVDA:OPT:20261127:145.0:P": {
                "sec_type": "OPT",
                "underlying": "NVDA",
                "expiry": "20261127",
                "strike": 145.0,
                "right": "P",
                "shares": 2.0,
            }
        }
        mock_ib.get_next_order_id.return_value = 333
        mock_ib.cancel_opposing_option_orders.return_value = 0
        mock_ib.us_option_contract.return_value = SimpleNamespace(
            symbol="NVDA", lastTradeDateOrContractMonth="20261127", strike=145.0, right="P"
        )
        worker.ib = mock_ib

        ord_row = {
            "id": "opt-sell-1",
            "ticker": "NVDA",
            "target_band": "OPT:20261127:145.0:P",
            "group_name": "OPTIONS_AUTONOMOUS",
            "direction": "sell",
            "order_type": "market",
            "shares": 2,
            "market_price": 4.20,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        orders_tbl = _make_chain([ord_row])
        sb = MagicMock()
        sb.table.side_effect = lambda name: orders_tbl if name == "stocks_orders" else _make_chain([])

        with patch.dict("sys.modules", _ibapi_sys_modules()), \
             patch.object(ibw, "get_supabase", return_value=sb), \
             patch("app.core.market_hours.is_options_market_open", return_value=(True, "OPEN")):
            worker.process_pending_orders()

        mock_ib.placeOrder.assert_called_once()

        # Y si tampoco hay contratos en retorno -> cancela con ANTI_SHORT_ZERO_POS y solicita reconciliación
        mock_ib.placeOrder.reset_mock()
        mock_ib.request_broker_positions.return_value = {}
        orders_tbl2 = _make_chain([ord_row])
        sb2 = MagicMock()
        sb2.table.side_effect = lambda name: orders_tbl2 if name == "stocks_orders" else _make_chain([])

        with patch.dict("sys.modules", _ibapi_sys_modules()), \
             patch.object(ibw, "get_supabase", return_value=sb2), \
             patch("app.core.market_hours.is_options_market_open", return_value=(True, "OPEN")):
            worker.process_pending_orders()

        mock_ib.placeOrder.assert_not_called()
        assert worker._reconcile_requested is True
    finally:
        ibw.PENDING_IB_ORDERS.clear()
        ibw.PENDING_IB_ORDERS.update(orig_pending)
        ibw.WORKING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.update(orig_working)


def test_on_ib_order_status_requests_async_reconcile_only():
    from app.workers import ib_bridge_worker as ibw

    orig_pending = dict(ibw.PENDING_IB_ORDERS)
    orig_active = ibw.ACTIVE_BRIDGE
    try:
        ibw.PENDING_IB_ORDERS.clear()
        ibw.PENDING_IB_ORDERS[401] = {
            "id": "ord-401",
            "ticker": "AAPL",
            "direction": "buy",
            "shares": 5,
            "market_price": 200.0,
        }
        bridge = ibw.IBBridgeWorker.__new__(ibw.IBBridgeWorker)
        bridge._reconcile_requested = False
        bridge.reconcile_broker_portfolio = MagicMock()
        ibw.ACTIVE_BRIDGE = bridge

        sb = MagicMock()
        sb.table.return_value = _make_chain([])

        with patch.object(ibw, "get_supabase", return_value=sb), \
             patch.object(ibw, "send_telegram_alert"):
            ibw.on_ib_order_status(401, {"status": "filled", "filled": 5, "avg_fill_price": 200.5})

        assert bridge._reconcile_requested is True
        bridge.reconcile_broker_portfolio.assert_not_called()
    finally:
        ibw.PENDING_IB_ORDERS.clear()
        ibw.PENDING_IB_ORDERS.update(orig_pending)
        ibw.ACTIVE_BRIDGE = orig_active


def test_get_next_order_id_and_req_id_threadsafe_disjoint():
    from app.data.ib_provider import IBConnection

    conn = IBConnection.__new__(IBConnection)
    conn.next_order_id = 100
    conn._next_req_id = 100000
    conn._id_lock = threading.Lock()

    order_ids = []
    req_ids = []
    lock = threading.Lock()

    def _worker():
        o_local = [conn.get_next_order_id() for _ in range(50)]
        r_local = [conn.get_next_req_id() for _ in range(50)]
        with lock:
            order_ids.extend(o_local)
            req_ids.extend(r_local)

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(order_ids) == 400 and len(set(order_ids)) == 400
    assert len(req_ids) == 400 and len(set(req_ids)) == 400
    assert max(order_ids) < 100000
    assert min(req_ids) >= 100000


def test_pre_order_live_quote_opra_and_no_opra_modes():
    from app.workers import ib_bridge_worker as ibw

    orig_pending = dict(ibw.PENDING_IB_ORDERS)
    orig_working = dict(ibw.WORKING_IB_ORDERS)
    try:
        # 1) Con OPRA quote vivo (bid=3.00, ask=3.20, rvol=2.5) -> LMT=3.20, TTL=45s
        ibw.PENDING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.clear()

        worker = ibw.IBBridgeWorker.__new__(ibw.IBBridgeWorker)
        mock_ib = MagicMock()
        mock_ib.connected = True
        mock_ib.get_next_order_id.return_value = 601
        mock_ib.us_option_contract.return_value = SimpleNamespace(
            symbol="NVDA", lastTradeDateOrContractMonth="20261127", strike=140.0, right="P"
        )
        mock_ib.get_contract_quote.return_value = {"bid": 3.00, "ask": 3.20}
        worker.ib = mock_ib

        ord_opra = {
            "id": "opt-buy-opra",
            "ticker": "NVDA",
            "target_band": "OPT:20261127:140.0:P",
            "group_name": "OPTIONS_AUTONOMOUS",
            "direction": "buy",
            "order_type": "limit",
            "shares": 2,
            "rvol": 2.5,
            "market_price": 2.80,
            "limit_price": 2.85,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        sb1 = MagicMock()
        sb1.table.side_effect = lambda n: _make_chain([ord_opra]) if n == "stocks_orders" else _make_chain([])

        with patch.dict("sys.modules", _ibapi_sys_modules()), \
             patch.object(ibw, "get_supabase", return_value=sb1), \
             patch("app.core.market_hours.is_options_market_open", return_value=(True, "OPEN")):
            worker.process_pending_orders()

        mock_ib.placeOrder.assert_called_once()
        placed_ord = mock_ib.placeOrder.call_args[0][2]
        assert placed_ord.orderType == "LMT"
        assert placed_ord.lmtPrice == 3.20
        assert ibw.WORKING_IB_ORDERS[601]["ttl_sec"] == 45.0

        # 2) Sin OPRA -> defecto lmt_wide_120s (TTL=120s)
        ibw.PENDING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.clear()
        mock_ib.placeOrder.reset_mock()
        mock_ib.get_next_order_id.return_value = 602
        mock_ib.get_contract_quote.return_value = {"bid": 0.0, "ask": 0.0}

        with patch.dict("sys.modules", _ibapi_sys_modules()), \
             patch.object(ibw, "get_supabase", return_value=sb1), \
             patch("app.core.market_hours.is_options_market_open", return_value=(True, "OPEN")):
            worker.process_pending_orders()

        assert ibw.WORKING_IB_ORDERS[602]["ttl_sec"] == 120.0
        assert ibw.WORKING_IB_ORDERS[602]["reprice_after_sec"] == 25.0

        # 3) Sin OPRA con opt_no_opra_exec_mode="mkt_liquid" en SPY -> cambia a MKT
        ibw.PENDING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.clear()
        mock_ib.placeOrder.reset_mock()
        mock_ib.get_next_order_id.return_value = 603
        mock_ib.us_option_contract.return_value = SimpleNamespace(
            symbol="SPY", lastTradeDateOrContractMonth="20261127", strike=600.0, right="P"
        )
        ord_spy = dict(ord_opra, ticker="SPY", shares=1, market_price=5.00, limit_price=5.05)

        def _sb_mkt(name):
            if name == "stocks_orders":
                return _make_chain([ord_spy])
            if name == "stocks_config":
                return _make_chain([{"value": "mkt_liquid"}])
            return _make_chain([])

        sb_mkt = MagicMock()
        sb_mkt.table.side_effect = _sb_mkt

        with patch.dict("sys.modules", _ibapi_sys_modules()), \
             patch.object(ibw, "get_supabase", return_value=sb_mkt), \
             patch("app.core.market_hours.is_options_market_open", return_value=(True, "OPEN")):
            worker.process_pending_orders()

        placed_mkt = mock_ib.placeOrder.call_args[0][2]
        assert placed_mkt.orderType == "MKT"
    finally:
        ibw.PENDING_IB_ORDERS.clear()
        ibw.PENDING_IB_ORDERS.update(orig_pending)
        ibw.WORKING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.update(orig_working)


def test_allow_after_hours_kv_and_stk_mkt_and_sell_watchdogs():
    from app.workers import ib_bridge_worker as ibw

    orig_pending = dict(ibw.PENDING_IB_ORDERS)
    orig_working = dict(ibw.WORKING_IB_ORDERS)
    try:
        ibw.PENDING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.clear()

        worker = ibw.IBBridgeWorker.__new__(ibw.IBBridgeWorker)
        worker._reconcile_requested = False
        mock_ib = MagicMock()
        mock_ib.connected = True
        mock_ib.get_next_order_id.return_value = 701
        mock_ib.us_stock_contract.return_value = SimpleNamespace(symbol="AAPL", secType="STK")
        worker.ib = mock_ib

        ord_stk = {
            "id": "stk-buy-701",
            "ticker": "AAPL",
            "direction": "buy",
            "order_type": "market",
            "shares": 2,
            "market_price": 120.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        sb = MagicMock()
        sb.table.side_effect = lambda n: _make_chain([ord_stk]) if n == "stocks_orders" else (
            _make_chain([{"value": "true"}]) if n == "stocks_config" else _make_chain([])
        )

        # allow_after_hours="true" via KV deja despachar BUY y la registra en WORKING_IB_ORDERS como STK MKT (ttl=45s)
        with patch.dict("sys.modules", _ibapi_sys_modules()), \
             patch.object(ibw, "get_supabase", return_value=sb), \
             patch("app.core.market_hours.is_market_open", return_value=(False, "CLOSED")):
            worker.process_pending_orders()

        mock_ib.placeOrder.assert_called_once()
        assert 701 in ibw.WORKING_IB_ORDERS
        assert ibw.WORKING_IB_ORDERS[701]["order_type"] == "MKT"
        assert ibw.WORKING_IB_ORDERS[701]["ttl_sec"] == 45.0

        # Watchdog STK MKT tras 45s cancela sin llamar compute_reprice_limit y retiene PENDING
        now_ts = time.time()
        ibw.WORKING_IB_ORDERS[701]["placed_at"] = now_ts - 50.0

        # Añadir también una orden SELL en WORKING abierta en TWS -> SELL WATCHDOG debe retener PENDING
        ibw.PENDING_IB_ORDERS[702] = {"id": "opt-sell-702", "ticker": "SPY", "direction": "sell", "shares": 1}
        ibw.WORKING_IB_ORDERS[702] = {
            "order_ctx": ibw.PENDING_IB_ORDERS[702],
            "is_option": True,
            "direction": "sell",
            "order_type": "MKT",
            "placed_at": now_ts - 100.0,
            "ttl_sec": 90.0,
        }
        mock_ib.request_open_orders.return_value = {702: {"status": "Submitted"}}

        with patch.object(ibw, "get_supabase", return_value=sb), \
             patch.object(ibw.time, "time", return_value=now_ts):
            worker.manage_working_orders(sweep_orphans=False)

        cancelled_oids = [c.args[0] for c in mock_ib.cancelOrder.call_args_list]
        assert 701 in cancelled_oids and 702 in cancelled_oids
        assert 701 not in ibw.WORKING_IB_ORDERS and 702 not in ibw.WORKING_IB_ORDERS
        assert ibw.PENDING_IB_ORDERS[701]["_cancel_reason_hint"] == "STK_MKT_WATCHDOG"
        assert ibw.PENDING_IB_ORDERS[702]["_cancel_reason_hint"] == "SELL_WATCHDOG_TIMEOUT"
    finally:
        ibw.PENDING_IB_ORDERS.clear()
        ibw.PENDING_IB_ORDERS.update(orig_pending)
        ibw.WORKING_IB_ORDERS.clear()
        ibw.WORKING_IB_ORDERS.update(orig_working)


def test_server_sweeper_and_multi_file_auto_reload():
    from app.workers.stocks_scheduler import cleanup_expired_pending_orders
    from app.workers.ib_bridge_worker import IBBridgeWorker

    ref_now = datetime(2026, 11, 20, 16, 0, 0, tzinfo=timezone.utc)
    pending_rows = [
        # Opción expirada por expires_at
        {"id": "exp-1", "ticker": "SPY", "target_band": "OPT:20261120:690.0:P", "status": "pending",
         "expires_at": (ref_now - timedelta(seconds=10)).isoformat(), "created_at": (ref_now - timedelta(seconds=100)).isoformat()},
        # Opción sin expires_at > 180s
        {"id": "exp-2", "ticker": "NVDA", "target_band": "OPT:20261127:140.0:P", "status": "pending",
         "expires_at": None, "created_at": (ref_now - timedelta(seconds=220)).isoformat()},
        # Acción sin expires_at > 900s
        {"id": "exp-3", "ticker": "AAPL", "target_band": None, "status": "pending",
         "expires_at": None, "created_at": (ref_now - timedelta(seconds=950)).isoformat()},
        # Opción fresca (30s) -> NO debe cancelarse
        {"id": "fresh-1", "ticker": "QQQ", "target_band": "OPT:20261127:610.0:P", "status": "pending",
         "expires_at": (ref_now + timedelta(seconds=60)).isoformat(), "created_at": (ref_now - timedelta(seconds=30)).isoformat()},
    ]
    tbl = _make_chain(pending_rows)
    sb = MagicMock()
    sb.table.return_value = tbl

    cancelled = cleanup_expired_pending_orders(sb=sb, now_dt=ref_now)
    assert cancelled == ["exp-1", "exp-2", "exp-3"]

    watched = IBBridgeWorker._get_watched_bridge_files()
    names = {w.replace("\\", "/").split("/")[-1] for w in watched}
    assert {"ib_bridge_worker.py", "ib_provider.py", "order_execution_plan.py", "broker_sync.py"} <= names
