"""
Tests for Bull Trend Expansion Intraday Ignition Scanner
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Añadir path backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.stocks.bull_expansion_scanner import (
    scan_single_ticker_bull_expansion,
    scan_universe_bull_expansion,
)


class TestBullExpansionScanner(unittest.TestCase):

    @patch("app.stocks.bull_expansion_scanner.evaluate_structural_regime")
    @patch("app.stocks.bull_expansion_scanner.get_live_1h_candle_and_sipv")
    @patch("app.stocks.bull_expansion_scanner.analyze_ticker_live_catalyst")
    def test_bull_expansion_with_catalyst(self, mock_catalyst, mock_live_1h, mock_regime):
        """Caso 1: En BULL_TREND_EXPANSION con 15m creciente Y catalizador Tier 1/2 -> Conviction MAXIMUM, rank >= 98"""
        mock_regime.return_value = {
            "regime_code": "BULL_TREND_EXPANSION",
            "current_price": 150.0,
            "room_to_bb_upper_pct": 5.0,
            "bb_upper": 160.0,
            "ema3": 151.0,
            "ema9": 148.0,
            "ema20": 145.0,
            "ema50": 140.0,
            "ema200": 130.0,
        }
        mock_live_1h.return_value = {
            "is_15m_high_growing": True,
            "vwap_intraday": 149.0,
            "day_open_price": 148.5,
            "upper_wick_ratio": 0.15,
            "is_15m_bb_breakout": True,
            "is_bb_15m_opening": True,
            "vol_decay_ratio_15m": 1.2,
        }
        mock_catalyst.return_value = {
            "tier": 1,
            "catalyst_name": "EARNINGS_BEAT",
            "headline": "Q3 Record Revenue Beat",
            "is_toxic": False,
        }

        res = scan_single_ticker_bull_expansion("NVDA", current_price=150.0)
        self.assertIsNotNone(res)
        self.assertEqual(res["ticker"], "NVDA")
        self.assertEqual(res["triggered_rule"], "STE_BULL_EXPANSION_CATALYST")
        self.assertEqual(res["conviction"], "MAXIMUM")
        self.assertTrue(res["has_news"])
        self.assertGreaterEqual(res["rank_score"], 98.0)
        self.assertTrue(res["is_15m_high_growing"])

    @patch("app.stocks.bull_expansion_scanner.evaluate_structural_regime")
    @patch("app.stocks.bull_expansion_scanner.get_live_1h_candle_and_sipv")
    @patch("app.stocks.bull_expansion_scanner.analyze_ticker_live_catalyst")
    def test_bull_expansion_without_catalyst(self, mock_catalyst, mock_live_1h, mock_regime):
        """Caso 2: En BULL_TREND_EXPANSION con 15m creciente SIN catalizador -> Califica por inercia técnica, Conviction HIGH, rank >= 90"""
        mock_regime.return_value = {
            "regime_code": "BULL_TREND_EXPANSION",
            "current_price": 220.0,
            "room_to_bb_upper_pct": 4.0,
            "bb_upper": 230.0,
            "ema3": 220.0,
            "ema9": 218.0,
            "ema20": 215.0,
            "ema50": 210.0,
            "ema200": 200.0,
        }
        mock_live_1h.return_value = {
            "is_15m_high_growing": True,
            "vwap_intraday": 219.0,
            "day_open_price": 218.0,
            "upper_wick_ratio": 0.20,
            "is_15m_bb_breakout": False,
            "is_bb_15m_opening": True,
            "vol_decay_ratio_15m": 1.0,
        }
        mock_catalyst.return_value = {
            "tier": 3,
            "catalyst_name": "",
            "headline": "",
            "is_toxic": False,
        }

        res = scan_single_ticker_bull_expansion("AAPL", current_price=220.0)
        self.assertIsNotNone(res)
        self.assertEqual(res["ticker"], "AAPL")
        self.assertEqual(res["triggered_rule"], "STE_BULL_EXPANSION_IGNITION")
        self.assertEqual(res["conviction"], "HIGH")
        self.assertFalse(res["has_news"])
        self.assertGreaterEqual(res["rank_score"], 90.0)

    @patch("app.stocks.bull_expansion_scanner.evaluate_structural_regime")
    def test_non_bull_expansion_rejected(self, mock_regime):
        """Caso 3: Régimen BEAR o CHOPPY es descartado de inmediato"""
        mock_regime.return_value = {
            "regime_code": "BEAR_TREND_EXPANSION",
            "current_price": 50.0,
        }
        res = scan_single_ticker_bull_expansion("INTC", current_price=50.0)
        self.assertIsNone(res)

    @patch("app.stocks.bull_expansion_scanner.evaluate_structural_regime")
    @patch("app.stocks.bull_expansion_scanner.get_live_1h_candle_and_sipv")
    def test_no_15m_growth_rejected(self, mock_live_1h, mock_regime):
        """Caso 4: Si la vela de 15m no marca nuevo máximo (High <= High anterior), se descarta"""
        mock_regime.return_value = {
            "regime_code": "BULL_TREND_EXPANSION",
            "current_price": 100.0,
            "room_to_bb_upper_pct": 5.0,
        }
        mock_live_1h.return_value = {
            "is_15m_high_growing": False,  # No hay ignición
            "vwap_intraday": 99.0,
            "day_open_price": 98.0,
            "upper_wick_ratio": 0.10,
        }
        res = scan_single_ticker_bull_expansion("TSLA", current_price=100.0)
        self.assertIsNone(res)

    @patch("app.stocks.bull_expansion_scanner.evaluate_structural_regime")
    @patch("app.stocks.bull_expansion_scanner.get_live_1h_candle_and_sipv")
    def test_below_vwap_rejected(self, mock_live_1h, mock_regime):
        """Caso 5: Si el precio cotiza por debajo de VWAP intradía, se rechaza para evitar trampas"""
        mock_regime.return_value = {
            "regime_code": "BULL_TREND_EXPANSION",
            "current_price": 100.0,
            "room_to_bb_upper_pct": 5.0,
        }
        mock_live_1h.return_value = {
            "is_15m_high_growing": True,
            "vwap_intraday": 105.0,  # Precio 100 < VWAP 105
            "day_open_price": 98.0,
            "upper_wick_ratio": 0.10,
        }
        res = scan_single_ticker_bull_expansion("MSFT", current_price=100.0)
        self.assertIsNone(res)

    @patch("app.stocks.bull_expansion_scanner.scan_single_ticker_bull_expansion")
    def test_scan_universe_sorting(self, mock_scan):
        """Caso 6: scan_universe_bull_expansion ordena por composite_rank descendente"""
        mock_scan.side_effect = lambda ticker: {
            "NVDA": {"ticker": "NVDA", "composite_rank": 98.0},
            "AAPL": {"ticker": "AAPL", "composite_rank": 91.0},
            "MSFT": {"ticker": "MSFT", "composite_rank": 95.0},
        }.get(ticker)

        ranked = scan_universe_bull_expansion(["AAPL", "NVDA", "MSFT"])
        self.assertEqual(len(ranked), 3)
        self.assertEqual([r["ticker"] for r in ranked], ["NVDA", "MSFT", "AAPL"])


if __name__ == "__main__":
    unittest.main()
