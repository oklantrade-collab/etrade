"""
Regression tests for Blindaje Operativo V4.1 (Forensic Fixes from 2026-11-23 Audit).
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _make_chain(data=None):
    c = MagicMock()
    c.select.return_value = c
    c.eq.return_value = c
    c.gte.return_value = c
    c.order.return_value = c
    c.limit.return_value = c
    c.upsert.return_value = c
    c.execute.return_value = SimpleNamespace(data=data if data is not None else [])
    return c


def test_warrior_momentum_options_uses_async_get_ohlcv_and_sync_fallback():
    from app.options import warrior_momentum_options as wmo
    from app.data.yfinance_provider import YFinanceProvider

    mock_yf = MagicMock()
    df_empty = pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
    mock_yf.get_ohlcv = AsyncMock(return_value=df_empty)
    mock_yf.get_historical_data = MagicMock(side_effect=AssertionError("Should call async get_ohlcv"))

    sb = MagicMock()
    sb.table.side_effect = lambda _n: _make_chain([])

    with patch.object(wmo, "get_supabase", return_value=sb), \
         patch.object(wmo, "YFinanceProvider", return_value=mock_yf):
        res = asyncio.run(wmo.run_warrior_momentum_options_scan(skip_time_window_check=True))

    assert res["ok"] is True
    assert res["count"] == 0
    assert mock_yf.get_ohlcv.await_count == len(wmo.WARRIOR_OPTIONS_UNIVERSE) * 2
    mock_yf.get_historical_data.assert_not_called()

    # Verify sync compatibility wrapper YFinanceProvider.get_historical_data
    idx = pd.date_range("2026-11-23 14:30:00", periods=8, freq="5min", tz="UTC")
    raw_hist = pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(8)],
            "High": [101.0 + i for i in range(8)],
            "Low": [99.5 + i for i in range(8)],
            "Close": [100.5 + i for i in range(8)],
            "Volume": [1000 * (i + 1) for i in range(8)],
        },
        index=idx,
    )
    raw_hist.index.name = "Datetime"

    with patch("app.data.yfinance_provider.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = raw_hist
        prov = YFinanceProvider()
        sync_df = prov.get_historical_data("SPY", period="3d", interval="5m", limit=5)

    assert sync_df is not None
    assert list(sync_df.columns) == ["open_time", "open", "high", "low", "close", "volume"]
    assert len(sync_df) == 5
    assert str(sync_df["open_time"].dt.tz) == "UTC"


def test_circuit_breaker_excludes_overnight_carryover_and_resets_et():
    from app.core import circuit_breaker as cb

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

    with patch.object(cb, "_today_et_str", return_value="2026-11-23"), \
         patch.object(cb, "get_supabase", return_value=sb_cb):
        # 1. Overnight Friday QQQ loss (-$915.72) closed on Monday morning MUST NOT trip global breaker
        state_after_carryover = cb.record_trade_completion(
            "QQQ",
            -915.72,
            sb=sb_cb,
            entry_time="2026-11-20T20:57:24+00:00",
            exit_time="2026-11-23T14:39:24+00:00",
        )
        assert state_after_carryover["tripped"] is False
        assert state_after_carryover["daily_realized_pnl"] == 0.0
        assert state_after_carryover["consecutive_losses"] == 0

        can_nvda, _ = cb.can_open_new_trade("NVDA", sb=sb_cb)
        assert can_nvda is True

        can_qqq, qqq_reason = cb.can_open_new_trade("QQQ", sb=sb_cb)
        assert can_qqq is False
        assert "cooldown" in qqq_reason.lower()

        # 2. Same-day intraday loss exceeding -$400 DOES trip global breaker
        state_after_intraday = cb.record_trade_completion(
            "AMD",
            -450.0,
            sb=sb_cb,
            entry_time="2026-11-23T14:45:00+00:00",
            exit_time="2026-11-23T15:10:00+00:00",
        )
        assert state_after_intraday["tripped"] is True
        assert state_after_intraday["daily_realized_pnl"] == -450.0
        can_nvda_blocked, _ = cb.can_open_new_trade("NVDA", sb=sb_cb)
        assert can_nvda_blocked is False

    # 3. ET date rollover resets tripped state cleanly
    with patch.object(cb, "_today_et_str", return_value="2026-11-24"), \
         patch.object(cb, "get_supabase", return_value=sb_cb):
        rolled = cb.get_circuit_breaker_state(sb=sb_cb)
        assert rolled["tripped"] is False
        assert rolled["daily_realized_pnl"] == 0.0
        assert rolled["consecutive_losses"] == 0
        assert rolled["last_reset_date"] == "2026-11-24"


def test_order_executor_daily_stop_unified_400_and_excludes_overnight_journal():
    from app.stocks import order_executor as oe

    cfg_chain = _make_chain([{"key": "paper_mode_active", "value": "true"}])
    journal_rows = [
        {"pnl_usd": -915.72, "entry_date": "2026-11-20T20:57:24+00:00", "exit_date": "2026-11-23T14:39:24+00:00"},
        {"pnl_usd": -125.00, "entry_date": "2026-11-23T14:40:00+00:00", "exit_date": "2026-11-23T15:00:00+00:00"},
    ]
    journal_chain = _make_chain(journal_rows)

    def _tbl(name):
        if name == "stocks_config":
            return cfg_chain
        if name == "trades_journal":
            return journal_chain
        return _make_chain([])

    sb = MagicMock()
    sb.table.side_effect = _tbl

    with patch.object(oe, "IB_AVAILABLE", False), \
         patch.object(oe, "get_supabase", return_value=sb):
        ex = oe.OrderExecutor()
        asyncio.run(ex.load_config())
        assert ex.max_daily_loss == 400.0

        daily_pnl = asyncio.run(ex._get_daily_pnl())
        assert daily_pnl == -125.0


def test_protect_the_win_queries_opt_paper_trades_and_computes_pnl_pct():
    from app.options.intraday_momentum_options_scanner import is_symbol_protected_by_win

    queried_tables = []

    def _sb_with_rows(rows):
        sb = MagicMock()

        def _table(name):
            queried_tables.append(name)
            return _make_chain(rows)

        sb.table.side_effect = _table
        return sb

    # 1. >= 10% ROI via realized_pnl / entry_total_invested locks symbol even if <= $100
    sb_pct_win = _sb_with_rows([
        {"id": 101, "status": "closed", "realized_pnl": 60.0, "entry_total_invested": 400.0, "exit_time": "2026-11-23T15:15:00+00:00"}
    ])
    prot1, msg1 = is_symbol_protected_by_win("AMD", sb_pct_win)
    assert prot1 is True
    assert "+15.0%" in msg1
    assert queried_tables[-1] == "opt_paper_trades"

    # 2. > $100 realized locks symbol even if ROI < 10%
    sb_usd_win = _sb_with_rows([
        {"id": 102, "status": "closed", "realized_pnl": 150.0, "entry_total_invested": 2000.0, "exit_time": "2026-11-23T15:20:00+00:00"}
    ])
    prot2, _ = is_symbol_protected_by_win("TSLA", sb_usd_win)
    assert prot2 is True

    # 3. < 10% AND <= $100 does not lock symbol
    sb_small = _sb_with_rows([
        {"id": 103, "status": "closed", "realized_pnl": 40.0, "entry_total_invested": 800.0, "exit_time": "2026-11-23T15:25:00+00:00"}
    ])
    prot3, _ = is_symbol_protected_by_win("NVDA", sb_small)
    assert prot3 is False


def test_eti_signals_migration_covers_eti_storage_upsert_fields():
    eti_storage_path = BACKEND_DIR / "app" / "options" / "eti_storage.py"
    migration_path = BACKEND_DIR / "migration_044_eti_signals_columns.sql"

    tree = ast.parse(eti_storage_path.read_text(encoding="utf-8"))
    row_data_keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "save_eti_signal":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for tgt in sub.targets:
                        if isinstance(tgt, ast.Name) and tgt.id == "row_data" and isinstance(sub.value, ast.Dict):
                            for k in sub.value.keys:
                                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                    row_data_keys.add(k.value)

    expected_added = {"signal_id", "status", "cadence", "asset_class", "action", "expires_at", "payload", "updated_at"}
    assert expected_added.issubset(row_data_keys)

    mig_sql = migration_path.read_text(encoding="utf-8")
    for col in expected_added:
        assert f"ADD COLUMN IF NOT EXISTS {col}" in mig_sql
    assert "uq_eti_signals_signal_id" in mig_sql
    assert "ON eti_signals(signal_id)" in mig_sql
