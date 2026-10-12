"""
Unit and Integration Tests — FASE 4: LIVE EXECUTION, CATALYST PIPELINE & TELEMETRY
==================================================================================
Valida:
1. Blindaje matemático: Stop Loss se mueve a Breakeven + 1.0% tras un cierre parcial.
2. Descarga y clasificación de noticias en vivo (fetch_ticker_news & analyze_ticker_live_catalyst).
3. Cierre forzoso EOD 15:50 ET en PositionMonitor (Cero Overnight).
4. Telemetría de catalizadores y niveles UPPER_5/6.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from zoneinfo import ZoneInfo
import pytest

from app.stocks.catalyst_classifier import (
    fetch_ticker_news,
    analyze_ticker_live_catalyst,
    classify_catalyst_text,
    analyze_news_items,
)
from app.stocks.position_monitor import PositionMonitor


# ══════════════════════════════════════════════════════════════════════════════
# 1. BLINDAJE MATEMÁTICO: BREAKEVEN + 1.0% TRAS CIERRE PARCIAL
# ══════════════════════════════════════════════════════════════════════════════

def test_breakeven_plus_one_percent_sl_lock():
    """
    Verifica que al ejecutar una salida parcial (ej. 50% en UPPER_5),
    el Stop Loss del remanente se actualiza automáticamente a Breakeven + 1.0%.
    """
    async def _run():
        monitor = PositionMonitor()
        trade = {
            "id": "pos_12345",
            "ticker": "RUNNER",
            "avg_price": 10.00,
            "entry_price": 10.00,
            "shares": 100,
            "shares_remaining": 100,
            "stop_loss": 9.50, # SL inicial al -5%
            "strategy": "INTRADAY_ALPHA",
        }
        exit_price = 11.00 # Cierre parcial con ganancia +10%
        shares_to_close = 50

        mock_sb = MagicMock()
        mock_table = MagicMock()
        mock_sb.table.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.insert.return_value = mock_table

        with patch("app.stocks.position_monitor.get_supabase", return_value=mock_sb), \
             patch("app.core.telegram_notifier.send_telegram", new_callable=AsyncMock):

            await monitor._execute_partial_close(
                trade=trade,
                exit_price=exit_price,
                shares_to_close=shares_to_close,
                block_name="block1",
                reason="TP50_UPPER_5"
            )

            # Verificar que se actualizó el stop loss a 10.00 * 1.01 = 10.10
            mock_table.update.assert_called()
            update_args = mock_table.update.call_args[0][0]
            assert update_args["stop_loss"] == 10.10
            assert update_args["sl_type"] == "breakeven_plus_1pct"
            assert update_args["shares_remaining"] == 50
            assert update_args["tp_block1_executed"] is True
            assert update_args["tp_block1_pnl"] == 50.00

    asyncio.run(_run())


# ══════════════════════════════════════════════════════════════════════════════
# 2. DESCARGA Y ANÁLISIS DE NOTICIAS EN VIVO
# ══════════════════════════════════════════════════════════════════════════════

def test_fetch_ticker_news_formatting():
    """Verifica que fetch_ticker_news extrae y formatea noticias correctamente."""
    mock_news_item = {
        "title": "BioCorp Announces FDA Breakthrough Designation for Oncology Asset",
        "publisher": "PR Newswire",
        "link": "https://example.com/news1",
        "summary": "Phase 2 oncology trial data"
    }

    class MockSearch:
        def __init__(self, query, news_count=5):
            self.news = [mock_news_item]

    with patch("yfinance.Search", side_effect=MockSearch):
        items = fetch_ticker_news("BIOC", max_items=5)
        assert len(items) == 1
        assert items[0]["title"] == mock_news_item["title"]
        assert items[0]["publisher"] == "PR Newswire"


def test_analyze_ticker_live_catalyst_classification():
    """Verifica que analyze_ticker_live_catalyst procesa las noticias en vivo y clasifica Tier 1."""
    mock_news_item = {
        "title": "Defense Dept Awards $85M Tactical Contract to Tech Systems",
        "publisher": "BusinessWire",
        "link": "https://example.com/contract",
        "summary": "Department of defense multi-year procurement"
    }

    class MockSearch:
        def __init__(self, query, news_count=5):
            self.news = [mock_news_item]

    with patch("yfinance.Search", side_effect=MockSearch):
        cat_info = analyze_ticker_live_catalyst("TECH")
        assert cat_info["tier"] == 1
        assert cat_info["catalyst_name"] == "TIER_1_TRANSFORMATIVE"
        assert cat_info["is_toxic"] is False


def test_analyze_ticker_live_catalyst_veto_dilution():
    """Verifica que analyze_ticker_live_catalyst veta de inmediato ante noticias de dilución."""
    mock_news_item = {
        "title": "MicroCorp Announces Pricing of $8M Public Offering of Common Stock and Warrants",
        "publisher": "GlobeNewswire",
        "link": "https://example.com/offering",
        "summary": "Offering priced at discount"
    }

    class MockSearch:
        def __init__(self, query, news_count=5):
            self.news = [mock_news_item]

    with patch("yfinance.Search", side_effect=MockSearch):
        cat_info = analyze_ticker_live_catalyst("MICR")
        assert cat_info["tier"] == 0
        assert cat_info["catalyst_name"] == "TOXIC_DILUTION_RISK"
        assert cat_info["is_toxic"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 3. POSITION MONITOR: CIERRE FORZOSO EOD 15:50 ET
# ══════════════════════════════════════════════════════════════════════════════

def test_position_monitor_eod_hard_exit_1550():
    """Verifica que PositionMonitor liquida al 100% una posición abierta a las 15:50 ET."""
    async def _run():
        monitor = PositionMonitor()
        trade = {
            "id": "pos_runner_eod",
            "ticker": "RUNNER",
            "avg_price": 10.00,
            "entry_price": 10.00,
            "shares": 200,
            "shares_remaining": 200,
            "stop_loss": 9.50,
        }

        ny_tz = ZoneInfo("America/New_York")
        # Viernes a las 15:52 ET
        nyc_1552 = datetime(2026, 10, 9, 15, 52, 0, tzinfo=ny_tz)

        mock_sb = MagicMock()
        mock_table = MagicMock()
        mock_sb.table.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.insert.return_value = mock_table

        mock_provider = MagicMock()
        mock_provider.get_ticker_info = AsyncMock(return_value={"current_price": 10.50})

        with patch("app.stocks.position_monitor.get_supabase", return_value=mock_sb), \
             patch("app.core.market_hours.get_nyc_now", return_value=nyc_1552), \
             patch("app.data.ib_provider.IBProvider.connect", side_effect=Exception("IB offline")), \
             patch("app.data.yfinance_provider.YFinanceProvider", return_value=mock_provider), \
             patch.object(monitor, "_close_position", new_callable=AsyncMock) as mock_close:

            # Llamar a _check_position
            await monitor._check_position(trade, stocks_config={})

            # Debe llamar inmediatamente a _close_position con 'eod_hard_exit_1550'
            mock_close.assert_called_once_with(trade, 10.50, "eod_hard_exit_1550")

    asyncio.run(_run())
