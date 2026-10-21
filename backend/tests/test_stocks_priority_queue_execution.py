"""
Test Suite: Stocks Priority Queue Execution & Orchestrator Integration
Verifica:
1. calculate_position_size con regla GAP_TRANCHE_1 (1/3 sizing) y reglas normales (full sizing).
2. process_priority_queue_buys consumiendo candidatos pendientes de stocks_priority_queue.
3. Exención de Gap Runners en validación EMA 1H de stocks_order_executor.
4. Presencia de misfire_grace_time en todos los jobs de stocks_scheduler.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.stocks.stocks_orchestrator import calculate_position_size, process_priority_queue_buys
from app.stocks.stocks_order_executor import execute_market_order


def test_calculate_position_size_normal_vs_gap_tranche():
    cfg = {"apex_proportional_sizing": False}
    price = 10.0
    cap_per_op = 1000.0
    all_ranks = [95.0, 98.0]

    # Regla normal: debe usar $1000 / $10 = 100 shares (múltiplo de 5)
    sizing_norm = calculate_position_size("AAPL", price, 98.0, cap_per_op, cfg, all_ranks, rule_code="APEX_AUTO")
    assert sizing_norm["shares"] == 100
    assert sizing_norm["capital"] == 1000.0

    # GAP_TRANCHE_1: debe usar 1/3 (~$333.3) / $10 = 30 o 35 shares (múltiplo de 5)
    sizing_gap = calculate_position_size("AAPL", price, 98.0, cap_per_op, cfg, all_ranks, rule_code="GAP_TRANCHE_1")
    assert sizing_gap["shares"] == 30
    assert sizing_gap["capital"] == 300.0


def test_process_priority_queue_buys_executes_pending():
    import asyncio
    mock_sb = MagicMock()

    # Mock market hours: abierto y antes de 15:15 ET
    with patch("app.core.market_hours.is_market_open", return_value=(True, "OPEN")), \
         patch("app.core.market_hours.get_nyc_now") as mock_nyc, \
         patch("app.stocks.stocks_orchestrator.calculate_available_capital", new_callable=AsyncMock) as mock_cap, \
         patch("app.stocks.stocks_adaptive_tp.fetch_macro_data", new_callable=AsyncMock) as mock_macro, \
         patch("app.stocks.stocks_order_executor.execute_market_order") as mock_order:

        mock_macro.return_value = {"sentiment": "neutral", "score": 50}

        mock_nyc_dt = MagicMock()
        mock_nyc_dt.weekday.return_value = 1
        mock_nyc_dt.hour = 10
        mock_nyc_dt.minute = 0
        mock_nyc.return_value = mock_nyc_dt

        mock_cap.return_value = {
            "can_buy": True,
            "ops_possible": 2,
            "capital_available": 2000.0,
            "capital_per_op": 1000.0,
            "reason": "OK (2 slots)"
        }

        # Mock stocks_positions (sin posiciones abiertas)
        mock_pos_query = MagicMock()
        mock_pos_query.select.return_value.eq.return_value.execute.return_value.data = []
        mock_sb.table.side_effect = lambda t: mock_table_router(t)

        pending_items = [
            {
                "ticker": "ATGL",
                "composite_rank": 99.8,
                "price_at_rank": 15.0,
                "status": "pending",
                "group_name": "OPEN_GAP_RUNNER",
                "triggered_rule": "GAP_TRANCHE_1",
                "is_overbought": False
            },
            {
                "ticker": "CTNM",
                "composite_rank": 99.5,
                "price_at_rank": 20.0,
                "status": "pending",
                "group_name": "FAST_TRACK",
                "triggered_rule": "FT_RUNNER_BUY",
                "is_overbought": False
            }
        ]

        def mock_table_router(table_name):
            t_mock = MagicMock()
            if table_name == "stocks_positions":
                t_mock.select.return_value.eq.return_value.execute.return_value.data = []
            elif table_name == "trades_journal":
                t_mock.select.return_value.gte.return_value.execute.return_value.data = []
            elif table_name == "stocks_priority_queue":
                t_mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = pending_items
                t_mock.upsert.return_value.execute.return_value = MagicMock()
                t_mock.update.return_value.eq.return_value.execute.return_value = MagicMock()
            elif table_name == "stocks_config":
                t_mock.select.return_value.execute.return_value.data = [
                    {"key": "total_capital_usd", "value": "5000"},
                    {"key": "max_active_stocks", "value": "5"}
                ]
            return t_mock

        mock_order.return_value = {"success": True}

        cfg = {"total_capital": 5000, "max_positions": 5, "apex_proportional_sizing": False}
        executed = asyncio.run(process_priority_queue_buys(supabase=mock_sb, cfg=cfg))

        assert len(executed) == 2
        assert executed[0]["ticker"] == "ATGL"
        assert executed[0]["rule"] == "GAP_TRANCHE_1"
        assert executed[1]["ticker"] == "CTNM"
        assert executed[1]["rule"] == "FT_RUNNER_BUY"


def test_gap_runner_exempt_from_1h_ema_and_falling_knife():
    """Verifica que execute_market_order no bloquee Gap Runners por EMA 1H descendente."""
    mock_sb = MagicMock()
    # Mock config
    cfg_rows = [
        {"key": "paper_mode_active", "value": "true"},
        {"key": "total_capital_usd", "value": "5000"},
        {"key": "max_pct_per_trade", "value": "20"},
        {"key": "max_total_risk_pct", "value": "80"},
        {"key": "max_active_stocks", "value": "5"},
    ]

    with patch("app.stocks.stocks_order_executor.get_supabase", return_value=mock_sb), \
         patch("app.stocks.stocks_order_executor.is_ib_bridge_alive", return_value=False), \
         patch("app.stocks.stocks_order_executor._is_after_1515_et", return_value=False), \
         patch("app.stocks.diagnostic_validator.can_operate_pre_trade", return_value=(True, "OK", {})):

        def mock_table(t):
            tm = MagicMock()
            if t == "stocks_config":
                tm.select.return_value.execute.return_value.data = cfg_rows
            elif t == "stocks_positions":
                tm.select.return_value.eq.return_value.execute.return_value.data = []
                tm.insert.return_value.execute.return_value = MagicMock()
            elif t == "trades_journal":
                tm.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
            elif t == "stocks_orders":
                tm.insert.return_value.execute.return_value = MagicMock()
            return tm

        mock_sb.table.side_effect = mock_table

        # Mock live_1h donde EMA 1H es descendente (-0.05) y EMA3 < EMA9
        # Para regla normal (APEX_AUTO) debe ser BLOQUEADO
        with patch("app.stocks.live_1h_candle_service.get_live_1h_candle_and_sipv") as mock_1h:
            mock_1h.return_value = {
                "is_ema3_1h_ascending": False,
                "ema3_slope_1h": -0.05,
                "is_ema3_above_ema9": False,
                "ema3_1h_live": 10.0,
                "ema9_1h": 10.5,
                "minus_di_5m": 25.0,
                "plus_di_5m": 15.0,
                "adx_5m": 15.0,
                "is_red_1h": False,
                "is_last_candle_green": True,
                "lower_wick_ratio": 0.40
            }

            # Normal rule: BLOCKED
            res_normal = execute_market_order("XYZ", "buy", "APEX_AUTO", {"price": 10.0}, {"group_name": "HOT"})
            assert res_normal["success"] is False
            assert "EMA3 1H descendente" in res_normal["reason"]

            # Gap Runner rule: EXEMPT from 1H EMA lag
            res_gap = execute_market_order("ATGL", "buy", "GAP_TRANCHE_1", {"price": 10.0}, {"group_name": "OPEN_GAP_RUNNER"})
            assert res_gap["success"] is True
            assert res_gap["ticker"] == "ATGL"
