"""
Pruebas de sincronización 1:1 Broker <-> Sistema y Trailing Stop Dinámico Ascendente:
1. Reconciliación de acción SHORT (QQQ -300) con signo correcto de PnL y sin borrado por tener opción.
2. Reapertura de opciones activas en TWS cerradas previamente sin SELL reciente (y fuera de 09:30-15:30 ET).
3. Liberación de `_in_flight_sells` cuando una orden SELL se cancela o falla.
4. `_close_position` de stocks nunca cierra en DB en modo offline/simulación si TWS sigue teniendo posición o snapshot está obsoleto.
5. Carrera bridge/monitor: `calculate_trailing_sl` detecta `trailing_sl > current_sl` incluso si `highest_price_reached` ya iguala `current_price`.
6. `compute_dynamic_stock_trailing_sl` sube continuamente en LONG (caso POWW) y baja en SHORT (caso QQQ) sin retroceder.
7. `calculate_1h_trailing_stop` no eleva el SL en pérdida pegado al precio (caso TTWO).
8. `exit_engine.evaluate_technical_rules_and_stops` nunca fija `stop_loss_underlying` por encima de `current_price` (CALL) ni por debajo (PUT).
9. Crypto `dynamic_sl_manager` no suspende el trailing durante tendencia alcista (`ema3_15m > ema9_15m`).
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _FakeQuery:
    def __init__(self, table_name: str, store: dict):
        self.table_name = table_name
        self.store = store
        self._op = "select"
        self._payload = None
        self._filters = []
        self._order_col = None
        self._order_desc = False
        self._limit = None

    def select(self, *_args, **_kwargs):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, set(vals)))
        return self

    def gt(self, col, val):
        self._filters.append(("gt", col, val))
        return self

    def gte(self, col, val):
        self._filters.append(("gte", col, val))
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self, row):
        for kind, col, val in self._filters:
            rv = row.get(col)
            if kind == "eq" and rv != val:
                return False
            if kind == "in" and rv not in val:
                return False
            if kind == "gt" and (rv is None or str(rv) <= str(val)):
                return False
            if kind == "gte" and (rv is None or str(rv) < str(val)):
                return False
        return True

    def execute(self):
        rows = self.store.setdefault(self.table_name, [])
        res = MagicMock()
        if self._op == "select":
            matched = [dict(r) for r in rows if self._matches(r)]
            if self._order_col:
                matched.sort(key=lambda r: str(r.get(self._order_col) or ""), reverse=self._order_desc)
            if self._limit is not None:
                matched = matched[:self._limit]
            res.data = matched
        elif self._op == "insert":
            item = dict(self._payload)
            item.setdefault("id", f"id-{len(rows)+1}")
            rows.append(item)
            res.data = [dict(item)]
        elif self._op == "update":
            updated = []
            for r in rows:
                if self._matches(r):
                    r.update(dict(self._payload))
                    updated.append(dict(r))
            res.data = updated
        elif self._op == "delete":
            self.store[self.table_name] = [r for r in rows if not self._matches(r)]
            res.data = []
        return res


class _FakeSupabase:
    def __init__(self, initial=None):
        self.store = {k: [dict(x) for x in v] for k, v in (initial or {}).items()}

    def table(self, name):
        return _FakeQuery(name, self.store)


def test_reconcile_imports_short_stock_qqq_and_reopens_closed_tws_options():
    from app.options.broker_sync import reconcile_with_ib_broker_portfolio

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    old_exit = (now_dt - timedelta(hours=3)).isoformat()

    portfolio = {
        "QQQ": {
            "symbol": "QQQ",
            "sec_type": "STK",
            "shares": -300.0,
            "avg_cost": 677.40,
            "market_price": 664.63,
            "unrealized_pnl": 3829.72,
        },
        "NVDA:OPT:20261118:180.0:C": {
            "symbol": "NVDA",
            "underlying": "NVDA",
            "sec_type": "OPT",
            "expiry": "20261118",
            "strike": 180.0,
            "right": "C",
            "shares": 1.0,
            "avg_cost": 250.0,
            "market_price": 3.10,
            "unrealized_pnl": 60.0,
        },
        "QQQ:OPT:20261120:660.0:P": {
            "symbol": "QQQ",
            "underlying": "QQQ",
            "sec_type": "OPT",
            "expiry": "20261120",
            "strike": 660.0,
            "right": "P",
            "shares": 1.0,
            "avg_cost": 400.0,
            "market_price": 4.20,
            "unrealized_pnl": 20.0,
        },
    }

    sb = _FakeSupabase({
        "stocks_config": [{"key": "ib_broker_portfolio", "value": repr(portfolio), "updated_at": now_iso}],
        "stocks_positions": [],
        "opt_underlyings": [{"id": 1, "symbol": "NVDA"}, {"id": 2, "symbol": "QQQ"}],
        "opt_paper_trades": [
            {
                "id": 1881,
                "symbol": "NVDA",
                "strategy_type": "long_call",
                "direction": "bullish",
                "status": "closed",
                "qty": 1,
                "expiry": "2026-11-18",
                "exit_time": old_exit,
                "exit_reason": "manual_simulated",
                "entry_fills": [{"strike": 180.0, "right": "C"}],
            }
        ],
        "stocks_orders": [],
    })

    res = reconcile_with_ib_broker_portfolio(sb, force=True, max_age_sec=86400.0)
    assert res["ok"] is True

    # QQQ SHORT debe sincronizarse con direction="short", shares=300, PnL positivo y no ser borrado aunque exista opción de QQQ
    stk_open = [p for p in sb.store["stocks_positions"] if p["status"] == "open"]
    assert len(stk_open) == 1
    qqq = stk_open[0]
    assert qqq["ticker"] == "QQQ"
    assert qqq["direction"] == "short"
    assert qqq["shares"] == 300
    assert qqq["unrealized_pnl"] == 3829.72
    assert qqq["stop_loss"] > qqq["current_price"]

    # Ambas opciones (incluida NVDA #1881 previamente cerrada sin SELL reciente) deben quedar abiertas con stop_loss_premium inicializado
    opt_open = [o for o in sb.store["opt_paper_trades"] if o["status"] == "open"]
    assert len(opt_open) == 2
    nvda_opt = next(o for o in opt_open if o["symbol"] == "NVDA")
    assert nvda_opt["id"] == 1881
    assert nvda_opt["exit_reason"] is None
    assert nvda_opt["exit_plan"]["stop_loss_premium"] > 0


def test_in_flight_sells_released_on_cancelled_status():
    from app.workers.ib_bridge_worker import IBBridgeWorker, on_ib_order_status, PENDING_IB_ORDERS, WORKING_IB_ORDERS
    import app.workers.ib_bridge_worker as bw

    worker = IBBridgeWorker.__new__(IBBridgeWorker)
    worker._in_flight_sells = {"PUBM": 20}
    prev_bridge = bw.ACTIVE_BRIDGE
    bw.ACTIVE_BRIDGE = worker

    PENDING_IB_ORDERS[9001] = {
        "id": "ord-pubm-1",
        "ticker": "PUBM",
        "direction": "sell",
        "shares": 20,
        "group_name": "STOCKS",
    }
    WORKING_IB_ORDERS[9001] = {"order_ctx": PENDING_IB_ORDERS[9001]}
    sb = _FakeSupabase({"stocks_orders": [{"id": "ord-pubm-1", "status": "submitted"}]})

    try:
        with patch("app.workers.ib_bridge_worker.get_supabase", return_value=sb):
            on_ib_order_status(9001, {"status": "cancelled", "filled": 0, "avg_fill_price": 0.0})
        assert worker._in_flight_sells["PUBM"] == 0
        assert sb.store["stocks_orders"][0]["status"] == "cancelled"
    finally:
        bw.ACTIVE_BRIDGE = prev_bridge
        PENDING_IB_ORDERS.pop(9001, None)
        WORKING_IB_ORDERS.pop(9001, None)


def test_execute_selected_candidate_broker_first_when_bridge_alive():
    from app.options import settings_defaults as sd
    from app.options.paper_execution import execute_selected_candidate_to_trade

    now_iso = datetime.now(timezone.utc).isoformat()
    sb = _FakeSupabase({
        "stocks_config": [{
            "key": "ib_bridge_heartbeat",
            "value": repr({"connected": True, "timestamp": now_iso}),
        }],
        "opt_paper_trades": [],
        "stocks_orders": [],
    })
    cand = {
        "id": 777,
        "underlying_id": 1,
        "symbol": "NVDA",
        "strategy_type": "long_call",
        "direction": "bullish",
        "qty": 1,
        "expiry": "2026-11-23",
        "legs": [
            {"strike": 150.0, "right": "C", "side": "buy", "bid": 3.0, "ask": 3.1, "market_data_type": "LIVE"},
        ],
        "entry_debit": 3.05,
        "max_loss_total": 305.0,
        "max_profit_contract": 500.0,
    }
    eff = sd.default_settings()
    eff["allow_delayed_data"] = True
    eff["max_open_risk_usd"] = 5000.0
    eff["max_risk_per_trade_usd"] = 1000.0

    det_now = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)
    with patch("app.options.paper_execution.is_market_open", return_value=(True, "OPEN")), \
         patch("app.options.options_aduana.validate_entry", return_value=MagicMock(approved=True)), \
         patch("app.core.circuit_breaker.can_open_new_trade", return_value=(True, "OK")), \
         patch("app.options.exit_engine.is_ticker_in_options_cooldown", return_value=(False, "")), \
         patch("app.core.structural_regime_engine.evaluate_macro_daily_bias", return_value={"veto_calls": False, "veto_puts": False}), \
         patch("app.core.structural_regime_engine.evaluate_structural_regime", return_value={"can_enter_call": True, "can_enter_put": True}), \
         patch("app.options.aduana_gap_runner_options.fetch_and_evaluate_options_gatekeeper", return_value={"approved": True}):
        res = execute_selected_candidate_to_trade(sb, cand, eff, und={"id": 1, "symbol": "NVDA", "event_flags": []}, now_dt=det_now)

    assert res is not None
    assert res["status"] == "order_dispatched"
    assert len(sb.store["opt_paper_trades"]) == 0
    assert len(sb.store["stocks_orders"]) == 1
    assert sb.store["stocks_orders"][0]["direction"] == "buy"


def test_stocks_close_position_never_simulates_close_when_offline():
    from app.stocks.position_monitor import PositionMonitor

    stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    sb = _FakeSupabase({
        "stocks_config": [{"key": "ib_broker_portfolio", "value": repr({"POWW": {"symbol": "POWW", "shares": 555}}), "updated_at": stale_ts}],
        "stocks_positions": [{"id": "pos-1", "ticker": "POWW", "direction": "long", "shares": 555, "avg_price": 2.69, "status": "open"}],
        "stocks_orders": [],
        "trades_journal": [],
    })
    pm = PositionMonitor()
    with patch("app.stocks.position_monitor.get_supabase", return_value=sb):
        asyncio.run(pm._close_position(sb.store["stocks_positions"][0], 2.75, "eod_hard_exit_1550"))

    assert sb.store["stocks_positions"][0]["status"] == "closing"
    assert len(sb.store["trades_journal"]) == 0
    assert len(sb.store["stocks_orders"]) == 1
    assert sb.store["stocks_orders"][0]["direction"] == "sell"


def test_trailing_sl_race_bridge_and_continuous_upward_poww():
    from app.strategy.dynamic_sl_manager import calculate_trailing_sl
    from app.stocks.position_monitor import compute_dynamic_stock_trailing_sl

    # Carrera: highest_price_reached ya fue subido por el bridge a 108.0 == current_price, pero SL quedó rezagado en 100.0
    pos = {
        "symbol": "NVDA",
        "side": "long",
        "highest_price_reached": 108.0,
        "stop_loss": 100.0,
        "trailing_sl_price": 100.0,
    }
    res = calculate_trailing_sl(pos, current_price=108.0, market_type="stocks_spot")
    assert res["improved"] is True
    assert res["trailing_sl_price"] > 100.0
    assert res["trailing_sl_price"] < 108.0

    # Caso POWW real: entry 2.692, initial SL 2.57 -> sube suavemente con cada subida y nunca retrocede
    sl = 2.57
    hi = 2.692
    sls = []
    for px in (2.764, 2.85, 2.95, 2.91, 3.10):
        hi = max(hi, px)
        new_sl, _ = compute_dynamic_stock_trailing_sl(2.692, px, highest_price=hi, current_sl=sl, side="long")
        assert new_sl >= sl
        assert new_sl < px
        sl = new_sl
        sls.append(sl)
    assert sls[0] > 2.57
    assert sls[1] > sls[0]
    assert sls[2] > sls[1]
    assert sls[3] == sls[2]  # Retroceso no baja el SL
    assert sls[4] > sls[3]

    # Caso QQQ SHORT: entry 677.40, SL inicial 704.50 -> baja dinámicamente conforme cae QQQ y no sube en rebote
    sl_s = 704.50
    lo = 664.63
    sls_s = []
    for px in (664.63, 640.0, 620.0, 625.0):
        lo = min(lo, px)
        new_sl_s, _ = compute_dynamic_stock_trailing_sl(677.40, px, current_sl=sl_s, side="short", lowest_price=lo)
        assert new_sl_s <= sl_s
        assert new_sl_s > px
        sl_s = new_sl_s
        sls_s.append(sl_s)
    assert sls_s[0] < 704.50
    assert sls_s[1] < sls_s[0]
    assert sls_s[2] < sls_s[1]
    assert sls_s[3] == sls_s[2]


def test_1h_trailing_does_not_tighten_in_loss_ttwo_case():
    from app.stocks.aduana_stocks_exit_engine import calculate_1h_trailing_stop

    df_1h = pd.DataFrame({
        "low": [217.0, 217.44, 217.50],
        "close": [218.0, 218.5, 217.45],
    })
    pos = {"side": "long", "avg_price": 221.80, "stop_loss": 212.93}
    res = calculate_1h_trailing_stop(pos, current_price=217.45, df_1h=df_1h)
    assert res["should_update"] is False


def test_options_underlying_sl_never_crosses_current_price():
    from app.options.exit_engine import evaluate_technical_rules_and_stops

    # CALL: EMA9 subiendo pero aún por encima del precio actual -> NO debe subir SL por encima de current_price
    pos_call = {
        "strategy_type": "long_call",
        "direction": "bullish",
        "symbol": "SPY",
        "exit_plan": {"stop_loss_underlying": 760.0, "trailing_sl_type": "INITIAL"},
    }
    tech_call = {
        "valid": True,
        "current_price": 768.0,
        "ema3_15m": 769.0,
        "ema9_15m": 768.8,
        "ema9_15m_rising": True,
        "cur_ema9_15m": 771.0,
        "prev_ema9_15m": 770.0,
        "ema3_slope_1h": 0.05,
        "rsi_1h": 55.0,
    }
    should_exit, _, info = evaluate_technical_rules_and_stops(pos_call, tech_call, datetime.now(timezone.utc))
    assert should_exit is False
    assert info["exit_plan"]["stop_loss_underlying"] < tech_call["current_price"]


def test_crypto_trailing_not_suspended_when_uptrending():
    from app.strategy.dynamic_sl_manager import calculate_trailing_sl

    df_up = pd.DataFrame({
        "ema1": [1900.0, 1920.0] * 6,
        "ema2": [1880.0, 1890.0] * 6,
    })
    pos = {
        "symbol": "ETHUSDT",
        "side": "LONG",
        "entry_price": 1840.0,
        "highest_price_reached": 1950.0,
        "sl_price": 1837.63,
    }
    with patch("app.core.memory_store.get_memory_df", return_value=df_up):
        res = calculate_trailing_sl(pos, current_price=1960.0, market_type="crypto_futures")
    assert res["improved"] is True
    assert res["highest_price_reached"] == 1960.0
    assert res["trailing_sl_price"] > 1837.63
