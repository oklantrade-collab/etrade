"""
Unit test for MicroPullbackEngine
Simulates a real-time 5-second bar stream resembling the GMAB setup at 08:40.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import MagicMock, patch
from app.stocks.micro_pullback_engine import MicroPullbackEngine, ScalpCandidateState

class TestMicroPullbackEngine(unittest.TestCase):

    def setUp(self):
        self.engine = MicroPullbackEngine()
        self.engine.daily_cushion_usd = 0.0 # Icebreaker active
        self.ticker = "GMAB"
        self.cand = ScalpCandidateState(self.ticker)
        self.engine.candidates[self.ticker] = self.cand

    def test_50_pct_rule_and_trigger(self):
        # 1. Simulate initial flat baseline at $45.00
        t0 = 1700000000
        for i in range(10):
            bar = {"time": t0 + (i*5), "open": 45.0, "high": 45.1, "low": 44.9, "close": 45.0, "volume": 1000}
            self.engine.process_5s_bar(self.ticker, bar)

        # 2. Simulate explosive impulse from $45.00 to $52.00 (+15.5%)
        impulse_prices = [45.5, 46.5, 48.0, 49.5, 51.0, 52.0]
        for idx, p in enumerate(impulse_prices):
            bar = {"time": t0 + 50 + (idx*5), "open": p - 0.5, "high": p, "low": p - 0.6, "close": p, "volume": 50000}
            self.engine.process_5s_bar(self.ticker, bar)

        self.assertEqual(self.cand.phase, "IMPULSE_DETECTED")
        self.assertAlmostEqual(self.cand.impulse_high, 52.0)
        self.assertAlmostEqual(self.cand.impulse_low, 44.9)

        # 3. Simulate Micro-Pullback (2 red bars) to $50.00 (half dollar, holds > 50% of 45-52 which is 48.5)
        # Bar 1 (Red): Open 52.0, High 52.1, Low 51.0, Close 51.0
        bar_red1 = {"time": t0 + 100, "open": 52.0, "high": 52.1, "low": 51.0, "close": 51.0, "volume": 15000}
        self.engine.process_5s_bar(self.ticker, bar_red1)
        self.assertEqual(self.cand.phase, "PULLBACK_OBSERVED")

        # Bar 2 (Red with bottoming tail): Open 51.0, High 51.2, Low 50.0, Close 50.5 (Wick from 50.0 to 50.5 is 0.5 / 1.2 = 41% wick)
        bar_red2 = {"time": t0 + 105, "open": 51.0, "high": 51.2, "low": 50.0, "close": 50.5, "volume": 20000}
        self.engine.process_5s_bar(self.ticker, bar_red2)
        self.assertTrue(self.cand.has_bottoming_tail)
        self.assertAlmostEqual(self.cand.pullback_low, 50.0)

        # 4. Trigger Bar (Green bar reversing above prev high 51.2): Open 50.5, High 51.5, Low 50.4, Close 51.4
        with patch.object(self.engine, "_calculate_scalp_shares", return_value=10), \
             patch("app.stocks.micro_pullback_engine.get_ib_connection") as mock_ib:
            mock_conn = MagicMock()
            mock_conn.connected = True
            mock_conn.get_next_order_id.return_value = 8888
            mock_conn.us_stock_contract.return_value = MagicMock()
            mock_ib.return_value = mock_conn

            bar_green = {"time": t0 + 110, "open": 50.5, "high": 51.5, "low": 50.4, "close": 51.4, "volume": 35000}
            self.engine.process_5s_bar(self.ticker, bar_green)

            # Verification: In-Trade triggered!
            self.assertTrue(self.cand.in_trade)
            self.assertAlmostEqual(self.cand.entry_price, 51.4)
            self.assertAlmostEqual(self.cand.stop_loss, 49.98) # 50.0 - 0.02
            self.assertAlmostEqual(self.cand.target_hod, 52.1)
            mock_conn.placeOrder.assert_called_once()
            print("✅ Micro-pullback trigger test PASSED! Order sent to TWS at LMT $51.42")

    def test_breakout_or_bailout_9_bars(self):
        # Put candidate in trade
        self.cand.in_trade = True
        self.cand.entry_price = 50.0
        self.cand.target_hod = 52.0
        self.cand.stop_loss = 48.0
        self.cand.shares = 10
        self.cand.bars_in_trade = 0
        self.engine.active_scalps[self.ticker] = self.cand

        with patch("app.stocks.micro_pullback_engine.get_ib_connection") as mock_ib:
            mock_conn = MagicMock()
            mock_conn.connected = True
            mock_conn.get_next_order_id.return_value = 9999
            mock_conn.us_stock_contract.return_value = MagicMock()
            mock_ib.return_value = mock_conn

            # Feed 8 bars stalling around 50.50 (less than 9)
            t0 = 1700000000
            for i in range(8):
                bar = {"time": t0 + (i*5), "open": 50.5, "high": 50.7, "low": 50.4, "close": 50.5, "volume": 5000}
                self.engine.process_5s_bar(self.ticker, bar)
                self.assertTrue(self.cand.in_trade)

            # 9th bar arrives and still hasn't broken HOD (52.0)
            bar9 = {"time": t0 + 40, "open": 50.5, "high": 50.6, "low": 50.3, "close": 50.4, "volume": 4000}
            self.engine.process_5s_bar(self.ticker, bar9)

            # Must have bailed out!
            self.assertFalse(self.cand.in_trade)
            mock_conn.placeOrder.assert_called_once()
            print("✅ Breakout or Bailout (9 bars = 45s) test PASSED! Sold position at stall.")

if __name__ == "__main__":
    unittest.main()
