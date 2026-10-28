"""
Unit test for MicroPullbackEngine & Aduana Open Gap Runner
Simulates:
1. Micro-Pullback trigger and 50% Fibonacci rule.
2. Breakout or Bailout (9 bars of 5s = 45s).
3. 3-Tier Cascade Exit (Tramo 1 50% HOD, Tramo 2 60% 15m runner, Tramo 3 40% 1H golden runner).
4. Rebuys on dip (max 3 rebuys).
5. Aduana Open Gap Runner 09:31:00 ET opening gate and Tier 1 Catalyst Priority Pass.
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.stocks.micro_pullback_engine import (
    MicroPullbackEngine,
    ScalpCandidateState,
    MAX_BAILOUT_BARS
)
from app.stocks.aduana_gap_runner_engine import evaluate_gap_runner_entry_tranches


class TestMicroPullbackAndGapRunner(unittest.TestCase):

    def setUp(self):
        self.engine = MicroPullbackEngine()
        self.engine.daily_cushion_usd = 0.0 # Icebreaker active
        self.ticker = "GMAB"
        self.cand = ScalpCandidateState(self.ticker)
        self.engine.candidates[self.ticker] = self.cand

    def test_50_pct_rule_and_trigger(self):
        """Impulso + Micro Pullback ordenado > 50% Fibo + Gatillo de compra."""
        t0 = 1700000000
        for i in range(10):
            bar = {"time": t0 + (i*5), "open": 45.0, "high": 45.1, "low": 44.9, "close": 45.0, "volume": 1000}
            self.engine.process_5s_bar(self.ticker, bar)

        # Impulso de $45.00 a $52.00
        impulse_prices = [45.5, 46.5, 48.0, 49.5, 51.0, 52.0]
        for idx, p in enumerate(impulse_prices):
            bar = {"time": t0 + 50 + (idx*5), "open": p - 0.5, "high": p, "low": p - 0.6, "close": p, "volume": 50000}
            self.engine.process_5s_bar(self.ticker, bar)

        self.assertEqual(self.cand.phase, "IMPULSE_DETECTED")
        self.assertAlmostEqual(self.cand.impulse_high, 52.0)
        self.assertAlmostEqual(self.cand.impulse_low, 44.9)

        # Micro-Pullback (2 barras rojas) hasta $50.00
        bar_red1 = {"time": t0 + 100, "open": 52.0, "high": 52.1, "low": 51.0, "close": 51.0, "volume": 15000}
        self.engine.process_5s_bar(self.ticker, bar_red1)
        self.assertEqual(self.cand.phase, "PULLBACK_OBSERVED")

        bar_red2 = {"time": t0 + 105, "open": 51.0, "high": 51.2, "low": 50.0, "close": 50.5, "volume": 20000}
        self.engine.process_5s_bar(self.ticker, bar_red2)
        self.assertTrue(self.cand.has_bottoming_tail)
        self.assertAlmostEqual(self.cand.pullback_low, 50.0)

        # Barra gatillo verde superando máximo previo
        with patch.object(self.engine, "_calculate_scalp_shares", return_value=100), \
             patch("app.stocks.micro_pullback_engine.get_ib_connection") as mock_ib:
            mock_conn = MagicMock()
            mock_conn.connected = True
            mock_conn.get_next_order_id.return_value = 8888
            mock_conn.us_stock_contract.return_value = MagicMock()
            mock_ib.return_value = mock_conn

            bar_green = {"time": t0 + 110, "open": 50.5, "high": 51.5, "low": 50.4, "close": 51.4, "volume": 35000}
            self.engine.process_5s_bar(self.ticker, bar_green)

            self.assertTrue(self.cand.in_trade)
            self.assertEqual(self.cand.phase, "IN_TRADE")
            self.assertAlmostEqual(self.cand.entry_price, 51.4)
            self.assertEqual(self.cand.shares, 100)
            self.assertEqual(self.cand.initial_shares, 100)
            self.assertAlmostEqual(self.cand.stop_loss, 49.98) # 50.0 - 0.02
            self.assertAlmostEqual(self.cand.target_hod, 52.1)
            mock_conn.placeOrder.assert_called_once()

    def test_breakout_or_bailout_9_bars(self):
        """Si transcurren 9 barras (45s) sin romper HOD, se aborta la posición."""
        self.cand.in_trade = True
        self.cand.phase = "IN_TRADE"
        self.cand.entry_price = 50.0
        self.cand.target_hod = 52.0
        self.cand.stop_loss = 48.0
        self.cand.shares = 100
        self.cand.initial_shares = 100
        self.cand.bars_in_trade = 0
        self.engine.active_scalps[self.ticker] = self.cand

        with patch("app.stocks.micro_pullback_engine.get_ib_connection") as mock_ib:
            mock_conn = MagicMock()
            mock_conn.connected = True
            mock_conn.get_next_order_id.return_value = 9999
            mock_conn.us_stock_contract.return_value = MagicMock()
            mock_ib.return_value = mock_conn

            # 8 barras estancadas en 50.50
            t0 = 1700000000
            for i in range(8):
                bar = {"time": t0 + (i*5), "open": 50.5, "high": 50.7, "low": 50.4, "close": 50.5, "volume": 5000}
                self.engine.process_5s_bar(self.ticker, bar)
                self.assertTrue(self.cand.in_trade)

            # Barra 9 llega y no rompió HOD (52.0)
            bar9 = {"time": t0 + 40, "open": 50.5, "high": 50.6, "low": 50.3, "close": 50.4, "volume": 4000}
            self.engine.process_5s_bar(self.ticker, bar9)

            # Debe haber hecho Bailout
            self.assertFalse(self.cand.in_trade)
            self.assertEqual(self.cand.shares, 0)
            mock_conn.placeOrder.assert_called_once()

    def test_cascade_exit_tramo_1_2_3(self):
        """Valida la cascada completa: Tramo 1 (50% HOD), Tramo 2 (60% runner en 15m), Tramo 3 (40% golden runner en 1H)."""
        self.cand.in_trade = True
        self.cand.phase = "IN_TRADE"
        self.cand.entry_price = 50.0
        self.cand.target_hod = 52.0
        self.cand.stop_loss = 48.0
        self.cand.shares = 100
        self.cand.initial_shares = 100
        self.cand.bars_in_trade = 2
        self.engine.active_scalps[self.ticker] = self.cand

        with patch("app.stocks.micro_pullback_engine.get_ib_connection") as mock_ib:
            mock_conn = MagicMock()
            mock_conn.connected = True
            mock_conn.get_next_order_id.return_value = 7777
            mock_conn.us_stock_contract.return_value = MagicMock()
            mock_ib.return_value = mock_conn

            # ── PASO 1: RUPTURA HOD -> Venta del 50% (50 acciones) ──
            bar_breakout = {"time": 1700000020, "open": 51.9, "high": 52.3, "low": 51.8, "close": 52.2, "volume": 60000}
            self.engine.process_5s_bar(self.ticker, bar_breakout)

            self.assertEqual(self.cand.shares, 50)
            self.assertEqual(self.cand.phase, "RUNNER_15M_MODE")
            self.assertAlmostEqual(self.cand.stop_loss, 50.02) # Breakeven entry + 0.02
            self.assertTrue(self.cand.in_trade)
            mock_conn.placeOrder.assert_called_once()
            args, _ = mock_conn.placeOrder.call_args
            ord_t1 = args[2]
            self.assertEqual(ord_t1.action, "SELL")
            self.assertEqual(ord_t1.totalQuantity, 50)

            # ── PASO 2: TRAMO 2 (Runner 15m) -> Venta del 60% del runner (30 acciones) al agotarse 15m ──
            mock_conn.reset_mock()
            with patch.object(self.engine, "_is_15m_trend_exhausted", return_value=True):
                bar_runner15 = {"time": 1700000025, "open": 52.5, "high": 52.6, "low": 52.0, "close": 52.1, "volume": 12000}
                self.engine.process_5s_bar(self.ticker, bar_runner15)

                self.assertEqual(self.cand.shares, 20) # 50 - 30 = 20
                self.assertEqual(self.cand.phase, "GOLDEN_RUNNER_1H_MODE")
                self.assertTrue(self.cand.in_trade)
                mock_conn.placeOrder.assert_called_once()
                args2, _ = mock_conn.placeOrder.call_args
                ord_t2 = args2[2]
                self.assertEqual(ord_t2.action, "SELL")
                self.assertEqual(ord_t2.totalQuantity, 30)

            # ── PASO 3: TRAMO 3 (Golden Runner 1H) -> Venta del 40% restante (20 acciones) al agotarse 1H ──
            mock_conn.reset_mock()
            with patch.object(self.engine, "_is_1h_trend_exhausted", return_value=True):
                bar_runner1h = {"time": 1700000030, "open": 53.0, "high": 53.0, "low": 51.5, "close": 51.8, "volume": 18000}
                self.engine.process_5s_bar(self.ticker, bar_runner1h)

                self.assertEqual(self.cand.shares, 0)
                self.assertFalse(self.cand.in_trade)
                self.assertEqual(self.cand.phase, "IDLE")
                mock_conn.placeOrder.assert_called_once()
                args3, _ = mock_conn.placeOrder.call_args
                ord_t3 = args3[2]
                self.assertEqual(ord_t3.action, "SELL")
                self.assertEqual(ord_t3.totalQuantity, 20)

    def test_rebuys_on_dip_max_3(self):
        """Valida que se permitan hasta 3 recompras en soporte EMA9/20 y se bloquee la 4ta."""
        self.cand.in_trade = True
        self.cand.phase = "RUNNER_15M_MODE"
        self.cand.entry_price = 50.0
        self.cand.shares = 50
        self.cand.initial_shares = 100
        self.cand.stop_loss = 50.02
        self.cand.rebuys_count = 0
        self.cand.last_rebuy_ts = 0.0
        self.engine.active_scalps[self.ticker] = self.cand

        with patch("app.stocks.micro_pullback_engine.get_ib_connection") as mock_ib, \
             patch("app.stocks.live_1h_candle_service.get_live_1h_candle_and_sipv") as mock_snap:
            mock_conn = MagicMock()
            mock_conn.connected = True
            mock_conn.get_next_order_id.return_value = 5555
            mock_conn.us_stock_contract.return_value = MagicMock()
            mock_ib.return_value = mock_conn

            # Snapshot alcista con EMA9 15m en $51.00
            mock_snap.return_value = {
                "is_ema3_above_ema9": True,
                "is_ema3_1h_ascending": True,
                "is_ema3_above_ema9_15m": True,
                "ema9_15m": 51.0,
                "ema3_slope_1h": 0.05
            }

            # Barra con rebote verde sobre EMA9 15m ($51.05) con mecha inferior
            bar_dip = {
                "time": 1700000000,
                "open": 50.8,
                "high": 51.3,
                "low": 50.7,
                "close": 51.1,
                "volume": 20000,
                "is_green": True,
                "lower_wick_ratio": 0.4
            }

            # Recompra 1
            self.cand.last_rebuy_ts = 0.0
            self.engine._check_rebuys_on_dip(self.cand, bar_dip)
            self.assertEqual(self.cand.rebuys_count, 1)
            self.assertEqual(self.cand.shares, 75) # 50 + 25

            # Recompra 2 (después de cooldown de 60s)
            self.cand.last_rebuy_ts = time.time() - 100.0
            self.engine._check_rebuys_on_dip(self.cand, bar_dip)
            self.assertEqual(self.cand.rebuys_count, 2)
            self.assertEqual(self.cand.shares, 100) # 75 + 25

            # Recompra 3
            self.cand.last_rebuy_ts = time.time() - 100.0
            self.engine._check_rebuys_on_dip(self.cand, bar_dip)
            self.assertEqual(self.cand.rebuys_count, 3)
            self.assertEqual(self.cand.shares, 125) # 100 + 25

            # Recompra 4 DEBE SER BLOQUEADA por límite de 3
            self.cand.last_rebuy_ts = time.time() - 100.0
            self.engine._check_rebuys_on_dip(self.cand, bar_dip)
            self.assertEqual(self.cand.rebuys_count, 3)
            self.assertEqual(self.cand.shares, 125)

    def test_aduana_open_gap_runner_0931_timing_gate(self):
        """Valida que la apertura a las 09:30 ET esté en pausa y se autorice a las 09:31 ET."""
        prices = [10.0, 9.8, 10.1, 9.9, 10.2, 10.1, 10.4, 10.7]
        df_5m = pd.DataFrame([
            {"open": p - 0.1, "high": p + 0.1, "low": p - 0.2, "close": p, "volume": 20000}
            for p in prices
        ])
        df_5m.iloc[-2] = {"open": 10.1, "high": 10.5, "low": 10.0, "close": 10.4, "volume": 40000}
        df_5m.iloc[-1] = {"open": 10.45, "high": 10.8, "low": 10.4, "close": 10.7, "volume": 60000}

        # Minuto 09:30 ET -> Pausa de asentamiento del 1er minuto
        res_0930 = evaluate_gap_runner_entry_tranches(
            ticker="POM",
            df_5m=df_5m,
            df_15m=None,
            df_1h=None,
            gap_pct=15.0,
            config={"skip_time_window_check": False, "skip_daily_runway_check": True, "current_et_time": (9, 30)}
        )
        self.assertFalse(res_0930["should_enter"])
        self.assertIn("Pausa de Asentamiento de Apertura (09:30 ET)", res_0930["reason"])

        # Minuto 09:31 ET -> Apertura autorizada
        res_0931 = evaluate_gap_runner_entry_tranches(
            ticker="POM",
            df_5m=df_5m,
            df_15m=None,
            df_1h=None,
            gap_pct=15.0,
            config={"skip_time_window_check": False, "skip_daily_runway_check": True, "current_et_time": (9, 31)}
        )
        self.assertTrue(res_0931["should_enter"])
        self.assertEqual(res_0931["tranche_step"], 1)

    def test_aduana_tier1_catalyst_priority_pass(self):
        """Valida que activos con catalizador Tier 1/2 reciban pase prioritario."""
        prices = [10.0, 9.8, 10.1, 9.9, 10.2, 10.1, 10.4, 10.7]
        df_5m = pd.DataFrame([
            {"open": p - 0.1, "high": p + 0.1, "low": p - 0.2, "close": p, "volume": 20000}
            for p in prices
        ])
        df_5m.iloc[-2] = {"open": 10.1, "high": 10.5, "low": 10.0, "close": 10.4, "volume": 40000}
        df_5m.iloc[-1] = {"open": 10.45, "high": 10.8, "low": 10.4, "close": 10.7, "volume": 60000}

        # 1H bajista de días anteriores donde EMA3 < EMA9
        c1h = [{"open": 12.0 - (i*0.1), "high": 12.1 - (i*0.1), "low": 11.8 - (i*0.1), "close": 11.9 - (i*0.1), "volume": 100000} for i in range(15)]
        df_1h_bearish = pd.DataFrame(c1h)

        # Caso Sin Catalizador (PR común / Tier 3): Falta de 1H alcista bloquea la entrada
        res_no_news = evaluate_gap_runner_entry_tranches(
            ticker="POM",
            df_5m=df_5m,
            df_15m=None,
            df_1h=df_1h_bearish,
            gap_pct=25.0,
            config={"skip_time_window_check": True, "skip_daily_runway_check": True},
            has_news=False,
            catalyst_tier=3
        )
        self.assertFalse(res_no_news["should_enter"])
        self.assertIn("Filtro mínimo 1H no cumplido", res_no_news["reason"])

        # Caso Con Catalizador Tier 1 (FDA / Earnings Beat): Pase prioritario concedido
        res_with_fda = evaluate_gap_runner_entry_tranches(
            ticker="POM",
            df_5m=df_5m,
            df_15m=None,
            df_1h=df_1h_bearish,
            gap_pct=25.0,
            config={"skip_time_window_check": True, "skip_daily_runway_check": True},
            has_news=True,
            catalyst_tier=1 # Tier 1 Super Catalyst (FDA)
        )
        self.assertTrue(res_with_fda["should_enter"])
        self.assertTrue(res_with_fda["catalyst_priority_pass"])
        self.assertEqual(res_with_fda["tranche_step"], 1)


if __name__ == "__main__":
    unittest.main()
