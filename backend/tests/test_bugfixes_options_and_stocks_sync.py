import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_parse_option_order_contract_key():
    from app.options.broker_sync import parse_option_order_contract_key

    assert parse_option_order_contract_key("AMZN", "OPT:20261113:270.0:C") == ("AMZN", "2026-11-13", 270.0, "C")
    assert parse_option_order_contract_key("MSFT:OPT:20261113:522.5:P", "") == ("MSFT", "2026-11-13", 522.5, "P")
    assert parse_option_order_contract_key("NVDA", "") is None


def test_find_existing_option_trade_blocks_only_recent_sell_cooldown_and_allows_older_tws_resync():
    from datetime import timedelta
    from app.options.broker_sync import find_existing_option_trade_for_contract

    now_dt = datetime.now(timezone.utc)
    recent_exit = (now_dt - timedelta(seconds=20)).isoformat()
    old_exit = (now_dt - timedelta(hours=2)).isoformat()

    rows_recent = [
        {
            "id": 100 - i,
            "symbol": "AMZN",
            "strategy_type": "long_call",
            "expiry": "2026-11-13",
            "status": "closed",
            "exit_time": recent_exit,
            "entry_fills": [{"strike": 250.0 + i * 2.5, "right": "C"}],
        }
        for i in range(8)
    ]

    mock_sb = MagicMock()

    def _table_side_effect(name):
        tbl = MagicMock()
        if name == "opt_paper_trades":
            tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = rows_recent
        elif name == "stocks_orders":
            # Consulta BUY posterior -> vacía
            tbl.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gt.return_value.limit.return_value.execute.return_value.data = []
            # Consulta SELL reciente -> filled hace 20s (debe activar cooldown anti-zombi <= 90s)
            tbl.select.return_value.eq.return_value.eq.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"id": "sell-1", "status": "filled", "filled_at": recent_exit, "created_at": recent_exit}
            ]
        return tbl

    mock_sb.table.side_effect = _table_side_effect

    ck_target = ("AMZN", "2026-11-13", 267.5, "C")  # index 7
    row, is_zombie = find_existing_option_trade_for_contract(mock_sb, ck_target, "long_call", limit=200)
    assert row is not None
    assert row["id"] == 93
    assert is_zombie is True

    # Ahora simular un cierre antiguo (>90s) sin orden SELL reciente: TWS sigue reportándolo -> NO debe bloquear reapertura
    rows_old = [{**rows_recent[7], "exit_time": old_exit}]
    def _table_side_effect_old(name):
        tbl = MagicMock()
        if name == "opt_paper_trades":
            tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = rows_old
        elif name == "stocks_orders":
            tbl.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gt.return_value.limit.return_value.execute.return_value.data = []
            tbl.select.return_value.eq.return_value.eq.return_value.eq.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return tbl

    mock_sb.table.side_effect = _table_side_effect_old
    row_old, is_zombie_old = find_existing_option_trade_for_contract(mock_sb, ck_target, "long_call", limit=200)
    assert row_old is not None
    assert row_old["id"] == 93
    assert is_zombie_old is False


def test_find_existing_option_trade_allows_newer_filled_buy():
    from app.options.broker_sync import find_existing_option_trade_for_contract

    rows = [
        {
            "id": 50,
            "symbol": "SPY",
            "strategy_type": "long_call",
            "expiry": "2026-11-13",
            "status": "closed",
            "exit_time": "2026-11-11T16:00:00+00:00",
            "entry_fills": [{"strike": 755.0, "right": "C"}],
        }
    ]
    mock_sb = MagicMock()

    def _table_side_effect(name):
        tbl = MagicMock()
        if name == "opt_paper_trades":
            tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = rows
        elif name == "stocks_orders":
            tbl.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gt.return_value.limit.return_value.execute.return_value.data = [{"id": "new-fill"}]
        return tbl

    mock_sb.table.side_effect = _table_side_effect
    row, is_zombie = find_existing_option_trade_for_contract(mock_sb, ("SPY", "2026-11-13", 755.0, "C"), "long_call")
    assert row is None
    assert is_zombie is False


def test_process_pending_orders_does_not_stick_processing_when_options_market_closed():
    from app.workers.ib_bridge_worker import IBBridgeWorker

    worker = IBBridgeWorker.__new__(IBBridgeWorker)
    worker.port = 7497
    worker.ib = MagicMock()
    worker.ib.connected = True
    worker.ib.us_option_contract.return_value = MagicMock(symbol="AMZN", lastTradeDateOrContractMonth="20261113", strike=270.0, right="C")

    pending_order = {
        "id": "ord-1",
        "ticker": "AMZN",
        "target_band": "OPT:20261113:270.0:C",
        "group_name": "OPTIONS",
        "direction": "sell",
        "order_type": "market",
        "shares": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [pending_order]

    with patch("app.workers.ib_bridge_worker.get_supabase", return_value=mock_sb), \
         patch("app.core.market_hours.is_options_market_open", return_value=(False, "CERRADO (Pre-Apertura)")):
        worker.process_pending_orders()

    assert mock_sb.table.return_value.update.call_count == 0
    assert worker.ib.placeOrder.call_count == 0


def test_cancel_opposing_option_orders_only_cancels_matching_buy():
    from app.data.ib_provider import IBConnection

    conn = IBConnection.__new__(IBConnection)
    conn.connected = True
    conn._open_orders = {}
    conn._open_orders_event = MagicMock()
    conn.cancelOrder = MagicMock()

    def _populate():
        contract_match = MagicMock(symbol="AMD", secType="OPT", lastTradeDateOrContractMonth="20261113", strike=540.0, right="C")
        order_match = MagicMock(action="BUY")
        state_live = MagicMock(status="Submitted")
        conn.openOrder(101, contract_match, order_match, state_live)

        contract_other = MagicMock(symbol="AMD", secType="OPT", lastTradeDateOrContractMonth="20261113", strike=530.0, right="C")
        conn.openOrder(102, contract_other, order_match, state_live)

        conn.openOrder(103, contract_match, MagicMock(action="SELL"), state_live)
        conn.openOrderEnd()

    conn.reqAllOpenOrders = MagicMock(side_effect=_populate)

    cancelled = conn.cancel_opposing_option_orders("AMD", "2026-11-13", 540.0, "C", closing_action="SELL", timeout=0.5)
    assert cancelled == 1
    conn.cancelOrder.assert_called_once_with(101)


def test_options_list_positions_counts_all_open_even_with_many_closed():
    from app.api.options import list_positions

    open_rows = [
        {"id": 999, "symbol": "AMZN", "strategy_type": "long_call", "expiry": "2026-11-13", "qty": 1, "entry_debit": 4.0, "entry_fills": [{"strike": 270.0, "right": "C"}], "unrealized_pnl": -100.0, "max_loss_total": 400.0, "status": "open"}
    ]
    closed_rows = [{"status": "closed", "realized_pnl": -50.0} for _ in range(500)]

    mock_sb = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "opt_paper_trades":
            def _select(*args, **kwargs):
                s = MagicMock()
                def _eq(col, val):
                    q = MagicMock()
                    if col == "status" and val == "open":
                        q.execute.return_value.data = open_rows
                        q.order.return_value.limit.return_value.execute.return_value.data = open_rows
                    elif col == "status" and val == "closed":
                        q.order.return_value.limit.return_value.execute.return_value.data = closed_rows
                    return q
                s.eq.side_effect = _eq
                return s
            t.select.side_effect = _select
        return t

    mock_sb.table.side_effect = _table

    with patch("app.api.options.get_supabase", return_value=mock_sb), \
         patch("app.options.broker_sync.reconcile_with_ib_broker_portfolio", return_value={}), \
         patch("app.options.broker_sync.load_broker_portfolio_snapshot", return_value=({}, 10.0)), \
         patch("app.api.options._load_stored", return_value=({}, None, None)):
        res = list_positions(status="open")

    assert res["summary"]["open_positions"] == 1
    assert res["summary"]["closed_positions"] == 500
