"""
Tests for Bear Rollover Intraday PUT Scanner
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Añadir path backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.stocks.bear_rollover_scanner import (
    scan_single_ticker_bear_rollover,
    scan_universe_bear_rollover,
)


class TestBearRolloverScanner(unittest.TestCase):

    @patch("app.stocks.bear_rollover_scanner.fetch_daily_metrics")
    @patch("app.stocks.bear_rollover_scanner.get_live_1h_candle_and_sipv")
    @patch("app.stocks.bear_rollover_scanner.analyze_ticker_live_bearish_catalyst")
    def test_bear_rollover_with_catalyst(self, mock_catalyst, mock_live_1h, mock_metrics):
        """Caso 1: En fondo bajista con rechazo en EMA9 y catalizador negativo -> Convicción MAXIMUM, rank >= 98"""
        mock_metrics.return_value = {
            "ema3": 98.0,
            "ema9": 100.0,
            "ema20": 105.0,
            "ema50": 110.0,
            "ema200": 120.0,
            "bb_lower": 88.0,
            "bb_upper": 112.0,
            "bb_bandwidth_pct": 28.0,
        }
        mock_live_1h.return_value = {
            "is_15m_high_growing": False,
            "is_15m_low_breaking": True,
            "is_red_candle_1h": True,
            "vwap_intraday": 99.5,
            "day_open_price": 99.0,
            "lower_wick_ratio": 0.12,
            "is_15m_bb_breakdown_lower": True,
            "is_bb_15m_opening": True,
        }
        mock_catalyst.return_value = {
            "tier": 1,
            "is_bearish": True,
            "catalyst_name": "EARNINGS_MISS_GUIDANCE_CUT",
            "headline": "Q3 Revenue Miss and Lowered FY Guidance",
        }

        res = scan_single_ticker_bear_rollover("INTC", current_price=98.0)
        self.assertIsNotNone(res)
        self.assertEqual(res["ticker"], "INTC")
        self.assertEqual(res["triggered_rule"], "OPT_BEAR_ROLLOVER_CATALYST")
        self.assertEqual(res["conviction"], "MAXIMUM")
        self.assertEqual(res["direction"], "bearish")
        self.assertTrue(res["has_news"])
        self.assertGreaterEqual(res["rank_score"], 98.0)
        self.assertEqual(res["recommended_option_strategy"], "bear_put_spread")

    @patch("app.stocks.bear_rollover_scanner.fetch_daily_metrics")
    @patch("app.stocks.bear_rollover_scanner.get_live_1h_candle_and_sipv")
    @patch("app.stocks.bear_rollover_scanner.analyze_ticker_live_bearish_catalyst")
    def test_bear_rollover_without_catalyst(self, mock_catalyst, mock_live_1h, mock_metrics):
        """Caso 2: En fondo bajista técnico sin catalizador -> Califica por inercia técnica, Convicción HIGH, rank >= 90"""
        mock_metrics.return_value = {
            "ema3": 195.0,
            "ema9": 197.0,
            "ema20": 200.0,
            "ema50": 205.0,
            "ema200": 215.0,
            "bb_lower": 180.0,
            "bb_upper": 210.0,
            "bb_bandwidth_pct": 20.0,
        }
        mock_live_1h.return_value = {
            "is_15m_high_growing": False,
            "is_15m_low_breaking": True,
            "is_red_candle_1h": True,
            "vwap_intraday": 196.0,
            "day_open_price": 196.5,
            "lower_wick_ratio": 0.15,
            "is_15m_bb_breakdown_lower": False,
            "is_bb_15m_opening": True,
        }
        mock_catalyst.return_value = {
            "tier": 3,
            "is_bearish": False,
            "catalyst_name": "",
        }

        res = scan_single_ticker_bear_rollover("BA", current_price=195.0)
        self.assertIsNotNone(res)
        self.assertEqual(res["ticker"], "BA")
        self.assertEqual(res["triggered_rule"], "OPT_BEAR_ROLLOVER_IGNITION")
        self.assertEqual(res["conviction"], "HIGH")
        self.assertFalse(res["has_news"])
        self.assertGreaterEqual(res["rank_score"], 90.0)

    @patch("app.stocks.bear_rollover_scanner.fetch_daily_metrics")
    def test_insufficient_room_to_bb_lower_rejected(self, mock_metrics):
        """Caso 3: Si ya está pegado al Bollinger Inferior (< 4.5%), se veta para no comprar PUTs en sobreventa"""
        mock_metrics.return_value = {
            "ema3": 101.0,
            "ema9": 105.0,
            "ema20": 110.0,
            "bb_lower": 100.0,  # Margen de caída apenas 1.0%
        }
        res = scan_single_ticker_bear_rollover("PYPL", current_price=101.0)
        self.assertIsNone(res)

    @patch("app.stocks.bear_rollover_scanner.fetch_daily_metrics")
    @patch("app.stocks.bear_rollover_scanner.get_live_1h_candle_and_sipv")
    def test_above_vwap_rejected(self, mock_live_1h, mock_metrics):
        """Caso 4: Si el precio cotiza por encima del VWAP intradía, es trampa de osos y se veta"""
        mock_metrics.return_value = {
            "ema3": 150.0,
            "ema9": 152.0,
            "ema20": 155.0,
            "ema50": 160.0,
            "bb_lower": 135.0,
        }
        mock_live_1h.return_value = {
            "is_15m_high_growing": False,
            "is_15m_low_breaking": True,
            "vwap_intraday": 148.0,  # Precio 150 > VWAP 148
            "day_open_price": 149.0,
            "lower_wick_ratio": 0.10,
        }
        res = scan_single_ticker_bear_rollover("TSLA", current_price=150.0)
        self.assertIsNone(res)

    @patch("app.stocks.bear_rollover_scanner.fetch_daily_metrics")
    @patch("app.stocks.bear_rollover_scanner.get_live_1h_candle_and_sipv")
    def test_lower_wick_absorption_rejected(self, mock_live_1h, mock_metrics):
        """Caso 5: Mecha inferior larga (>= 0.35) indica compras absorbiendo mínimos -> se veta"""
        mock_metrics.return_value = {
            "ema3": 50.0,
            "ema9": 52.0,
            "ema20": 55.0,
            "ema50": 60.0,
            "bb_lower": 44.0,
        }
        mock_live_1h.return_value = {
            "is_15m_high_growing": False,
            "is_15m_low_breaking": True,
            "vwap_intraday": 51.0,
            "day_open_price": 51.5,
            "lower_wick_ratio": 0.42,  # Absorción compradora
        }
        res = scan_single_ticker_bear_rollover("AAL", current_price=50.0)
        self.assertIsNone(res)

    @patch("app.stocks.bear_rollover_scanner.scan_single_ticker_bear_rollover")
    def test_scan_universe_sorting(self, mock_scan):
        """Caso 6: scan_universe_bear_rollover ordena por composite_rank descendente"""
        mock_scan.side_effect = lambda ticker: {
            "INTC": {"ticker": "INTC", "composite_rank": 98.0},
            "BA": {"ticker": "BA", "composite_rank": 92.0},
            "PYPL": {"ticker": "PYPL", "composite_rank": 95.0},
        }.get(ticker)

        ranked = scan_universe_bear_rollover(["BA", "INTC", "PYPL"])
        self.assertEqual(len(ranked), 3)
        self.assertEqual([r["ticker"] for r in ranked], ["INTC", "PYPL", "BA"])


if __name__ == "__main__":
    unittest.main()
