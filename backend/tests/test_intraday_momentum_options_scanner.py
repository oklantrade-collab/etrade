"""
Unit tests for Intraday Momentum OTM -> ITM Options Scanner & Contract Picker
"""

import os
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.options.opt_contract_picker import select_best_option_contract
from app.options.intraday_momentum_options_scanner import evaluate_intraday_momentum_breakout
from app.options.autonomous_options_dispatcher import dispatch_autonomous_option_trade


class TestIntradayMomentumOptions(unittest.TestCase):

    def setUp(self):
        self.today = date.today()

    def test_otm_momentum_contract_picker_selects_delta_35_otm_call(self):
        """Valida que en modo OTM_MOMENTUM se seleccione el strike OTM (Delta ~0.35, 1-3 DTE) y no el ATM/ITM."""
        exp = self.today + timedelta(days=3) # Vencimiento semanal a 3 días
        contracts = [
            # Strike 100: ATM (Delta 0.52) - Ideal para Gap Runner pero NO para OTM Momentum
            {
                "contract_id": 101, "conid": 101, "symbol": "AMD", "right": "C",
                "strike": 100.0, "expiry": exp.isoformat(), "bid": 3.40, "ask": 3.50,
                "delta": 0.52, "open_interest": 2500, "volume": 1200
            },
            # Strike 103: OTM Óptimo (Delta 0.35) - Sweet spot Gamma ignition
            {
                "contract_id": 102, "conid": 102, "symbol": "AMD", "right": "C",
                "strike": 103.0, "expiry": exp.isoformat(), "bid": 1.45, "ask": 1.50,
                "delta": 0.35, "open_interest": 4000, "volume": 3500
            },
            # Strike 110: Deep OTM (Delta 0.12) - Demasiado lejos
            {
                "contract_id": 103, "conid": 103, "symbol": "AMD", "right": "C",
                "strike": 110.0, "expiry": exp.isoformat(), "bid": 0.20, "ask": 0.25,
                "delta": 0.12, "open_interest": 1000, "volume": 300
            }
        ]

        # 1. En modo GAP_RUNNER tradicional elige el ATM (strike 100)
        best_gap, _ = select_best_option_contract(
            contracts=contracts,
            underlying_price=100.0,
            direction="CALL",
            selection_mode="GAP_RUNNER",
            now_date=self.today
        )
        self.assertIsNotNone(best_gap)
        self.assertEqual(best_gap.strike, 100.0)
        self.assertEqual(best_gap.delta, 0.52)

        # 2. En modo OTM_MOMENTUM elige el OTM (strike 103, delta 0.35)
        best_otm, _ = select_best_option_contract(
            contracts=contracts,
            underlying_price=100.0,
            direction="CALL",
            selection_mode="OTM_MOMENTUM",
            now_date=self.today
        )
        self.assertIsNotNone(best_otm)
        self.assertEqual(best_otm.strike, 103.0)
        self.assertEqual(best_otm.delta, 0.35)

    def test_otm_momentum_contract_picker_selects_delta_35_otm_put(self):
        """Valida selección de PUT OTM (Delta ~ -0.35, strike debajo de spot)."""
        exp = self.today + timedelta(days=4)
        contracts = [
            # Strike 100: ATM (Delta -0.50)
            {
                "contract_id": 201, "conid": 201, "symbol": "TSLA", "right": "P",
                "strike": 100.0, "expiry": exp.isoformat(), "bid": 3.00, "ask": 3.10,
                "delta": -0.50, "open_interest": 1500, "volume": 900
            },
            # Strike 97: OTM Óptimo (Delta -0.34)
            {
                "contract_id": 202, "conid": 202, "symbol": "TSLA", "right": "P",
                "strike": 97.0, "expiry": exp.isoformat(), "bid": 1.30, "ask": 1.35,
                "delta": -0.34, "open_interest": 3000, "volume": 2000
            }
        ]

        best_put, _ = select_best_option_contract(
            contracts=contracts,
            underlying_price=100.0,
            direction="PUT",
            selection_mode="OTM_MOMENTUM",
            now_date=self.today
        )
        self.assertIsNotNone(best_put)
        self.assertEqual(best_put.strike, 97.0)
        self.assertEqual(best_put.delta, -0.34)

    def test_evaluate_intraday_breakout_call_qualified(self):
        """Valida calificación exitosa de CALL en ORB 15M breakout con 1H EMA3 > EMA9."""
        # 15m velas: primera vela [100.0 a 102.0], segunda vela rompiendo a 103.0
        df_15m = pd.DataFrame({
            "open": [100.0, 102.0],
            "high": [102.0, 103.5],
            "low": [99.5, 101.8],
            "close": [101.8, 103.2],
            "volume": [1_000_000, 1_200_000]
        })
        # 5m velas cotizando a 103.2 (> ORB High de 102.0 y > VWAP)
        df_5m = pd.DataFrame({
            "open": [100.0, 101.0, 101.5, 102.0, 102.5, 102.8, 102.9],
            "high": [101.2, 101.8, 102.2, 102.6, 103.0, 103.3, 103.5],
            "low": [99.8, 100.8, 101.2, 101.8, 102.2, 102.6, 102.8],
            "close": [101.0, 101.5, 102.0, 102.5, 102.8, 103.0, 103.2],
            "volume": [100_000, 120_000, 110_000, 150_000, 180_000, 200_000, 350_000]
        })

        res = evaluate_intraday_momentum_breakout(
            symbol="AMD",
            df_5m=df_5m,
            df_15m=df_15m,
            is_ema3_above_ema9_1h=True
        )

        self.assertTrue(res["is_qualified"])
        self.assertEqual(res["direction"], "CALL")
        self.assertGreaterEqual(res["score"], 70.0)
        self.assertIn("ORB_15M_BREAKOUT", res["triggers"])

    def test_evaluate_intraday_breakout_fail_closed_choke_point_blocks_call(self):
        """Valida que si en 1H EMA3 <= EMA9, el Choke Point bloquee incondicionalmente el CALL."""
        df_15m = pd.DataFrame({
            "open": [100.0, 102.0],
            "high": [102.0, 103.5],
            "low": [99.5, 101.8],
            "close": [101.8, 103.2],
            "volume": [1_000_000, 1_200_000]
        })
        df_5m = pd.DataFrame({
            "open": [100.0, 101.0, 101.5, 102.0, 102.5, 102.8, 102.9],
            "high": [101.2, 101.8, 102.2, 102.6, 103.0, 103.3, 103.5],
            "low": [99.8, 100.8, 101.2, 101.8, 102.2, 102.6, 102.8],
            "close": [101.0, 101.5, 102.0, 102.5, 102.8, 103.0, 103.2],
            "volume": [100_000, 120_000, 110_000, 150_000, 180_000, 200_000, 350_000]
        })

        # 1H es bajista (is_ema3_above_ema9_1h=False)
        res = evaluate_intraday_momentum_breakout(
            symbol="AMD",
            df_5m=df_5m,
            df_15m=df_15m,
            is_ema3_above_ema9_1h=False
        )

        self.assertFalse(res["is_qualified"])
        self.assertIn("No cumple", res["reason"])

    def test_evaluate_intraday_breakout_put_qualified(self):
        """Valida calificación de PUT en ORB 15M breakdown con 1H EMA3 < EMA9."""
        df_15m = pd.DataFrame({
            "open": [100.0, 98.0],
            "high": [100.5, 98.2],
            "low": [98.0, 96.5],
            "close": [98.2, 96.8],
            "volume": [1_000_000, 1_200_000]
        })
        df_5m = pd.DataFrame({
            "open": [100.0, 99.0, 98.5, 98.0, 97.5, 97.2, 97.0],
            "high": [100.2, 99.2, 98.8, 98.2, 97.8, 97.4, 97.1],
            "low": [98.8, 98.2, 97.8, 97.2, 96.8, 96.6, 96.4],
            "close": [99.0, 98.5, 98.0, 97.5, 97.1, 96.8, 96.6],
            "volume": [100_000, 120_000, 110_000, 150_000, 180_000, 200_000, 350_000]
        })

        res = evaluate_intraday_momentum_breakout(
            symbol="TSLA",
            df_5m=df_5m,
            df_15m=df_15m,
            is_ema3_above_ema9_1h=False
        )

        self.assertTrue(res["is_qualified"])
        self.assertEqual(res["direction"], "PUT")
        self.assertIn("ORB_15M_BREAKDOWN", res["triggers"])

    @patch("app.options.autonomous_options_dispatcher.send_telegram_alert")
    @patch("app.options.autonomous_options_dispatcher.fetch_and_select_best_option_contract")
    def test_dispatcher_with_otm_momentum_configures_tp1_tp2_and_sl(self, mock_picker, mock_alert):
        """Valida que dispatch_autonomous_option_trade configure TP1 +50%, TP2 +100% y SL -35% en modo OTM_MOMENTUM."""
        mock_contract = MagicMock()
        mock_contract.symbol = "AMD"
        mock_contract.right = "C"
        mock_contract.strike = 105.0
        mock_contract.expiry = date(2026, 11, 2)
        mock_contract.dte = 5
        mock_contract.bid = 2.00
        mock_contract.ask = 2.10
        mock_contract.mid = 2.05
        mock_contract.conid = 777333
        mock_contract.contract_id = 777333
        mock_contract.tranche_1_contracts = 2

        mock_picker.return_value = (mock_contract, [])

        mock_sb = MagicMock()
        mock_sb.table().select().eq().eq().execute.return_value.data = []
        mock_sb.table().select().like().in_().execute.return_value.data = []
        mock_sb.table().insert().execute.return_value.data = [{"id": "ord_otm_456"}]

        cand = {
            "ticker": "AMD",
            "price": 100.0,
            "selection_mode": "OTM_MOMENTUM",
            "triggered_rule": "MOMENTUM_OTM_ITM_CALL",
            "conviction": "HIGH",
            "entry_reason": "ORB 15M Breakout + 1H EMA3>EMA9"
        }

        res = dispatch_autonomous_option_trade(cand, direction="CALL", config={"options_trade_budget_usd": 1000}, supabase=mock_sb)

        self.assertTrue(res["success"])
        # Verificar que se insertó en opt_paper_trades con TP1 (+50% = $3.15) y TP2 (+100% = $4.20)
        inserts = [c[0][0] for c in mock_sb.table().insert.call_args_list if c[0]]
        paper_call_args = next(p for p in inserts if "exit_plan" in p)
        self.assertEqual(paper_call_args["exit_plan"]["selection_mode"], "OTM_MOMENTUM")
        self.assertEqual(paper_call_args["exit_plan"]["tp1_target_premium"], round(2.10 * 1.50, 2))
        self.assertEqual(paper_call_args["exit_plan"]["tp2_target_premium"], round(2.10 * 2.00, 2))
        self.assertEqual(paper_call_args["exit_plan"]["hard_sl_premium"], round(2.10 * 0.65, 2))


if __name__ == "__main__":
    unittest.main()
