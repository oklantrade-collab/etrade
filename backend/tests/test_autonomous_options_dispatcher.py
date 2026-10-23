"""
Unit tests for Autonomous Options Dispatcher (CALLs & PUTs -> TWS)
"""

import sys
import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.options.autonomous_options_dispatcher import dispatch_autonomous_option_trade


class TestAutonomousOptionsDispatcher(unittest.TestCase):

    def setUp(self):
        self.mock_sb = MagicMock()
        # Defaults para evitar duplicados
        self.mock_sb.table().select().eq().eq().execute.return_value.data = []
        self.mock_sb.table().select().like().in_().execute.return_value.data = []
        self.mock_sb.table().insert().execute.return_value.data = [{"id": "ord_mock_123"}]

    @patch("app.options.autonomous_options_dispatcher.send_telegram_alert")
    @patch("app.options.autonomous_options_dispatcher.fetch_and_select_best_option_contract")
    def test_dispatch_call_success(self, mock_picker, mock_alert):
        """Caso 1: Despacho exitoso de CALL para candidato Bull Expansion"""
        mock_contract = MagicMock()
        mock_contract.symbol = "NVDA"
        mock_contract.right = "C"
        mock_contract.strike = 150.0
        mock_contract.expiry = date(2026, 11, 6)
        mock_contract.dte = 14
        mock_contract.bid = 4.40
        mock_contract.ask = 4.50
        mock_contract.mid = 4.45
        mock_contract.conid = 999111
        mock_contract.contract_id = 999111
        mock_contract.tranche_1_contracts = 2

        mock_picker.return_value = (mock_contract, [])

        cand = {
            "ticker": "NVDA",
            "price": 150.0,
            "triggered_rule": "STE_BULL_EXPANSION_CATALYST",
            "conviction": "MAXIMUM",
            "entry_reason": "Vela 15m nuevo máximo en Bull Trend Expansion",
        }

        res = dispatch_autonomous_option_trade(cand, direction="CALL", config={"options_trade_budget_usd": 1500}, supabase=self.mock_sb)

        self.assertTrue(res["success"])
        self.assertEqual(res["order_id"], "ord_mock_123")
        self.assertEqual(res["contracts"], 2)
        self.assertEqual(res["price"], 4.50)
        self.assertIn("NVDA:OPT:20261106:150.0:C", res["ticker"])
        mock_alert.assert_called_once()

    @patch("app.options.autonomous_options_dispatcher.send_telegram_alert")
    @patch("app.options.autonomous_options_dispatcher.fetch_and_select_best_option_contract")
    def test_dispatch_put_success(self, mock_picker, mock_alert):
        """Caso 2: Despacho exitoso de PUT para candidato Bear Rollover"""
        mock_contract = MagicMock()
        mock_contract.symbol = "INTC"
        mock_contract.right = "P"
        mock_contract.strike = 98.0
        mock_contract.expiry = date(2026, 11, 6)
        mock_contract.dte = 14
        mock_contract.bid = 2.05
        mock_contract.ask = 2.10
        mock_contract.mid = 2.08
        mock_contract.conid = 888222
        mock_contract.contract_id = 888222
        mock_contract.tranche_1_contracts = 3

        mock_picker.return_value = (mock_contract, [])

        cand = {
            "ticker": "INTC",
            "price": 98.0,
            "direction": "bearish",
            "triggered_rule": "OPT_BEAR_ROLLOVER_CATALYST",
            "conviction": "MAXIMUM",
            "entry_reason": "Rechazo en EMA9 con quiebre de mínimos 15m",
        }

        res = dispatch_autonomous_option_trade(cand, direction="PUT", config={"options_trade_budget_usd": 1000}, supabase=self.mock_sb)

        self.assertTrue(res["success"])
        self.assertEqual(res["contracts"], 3)
        self.assertEqual(res["price"], 2.10)
        self.assertIn("INTC:OPT:20261106:98.0:P", res["ticker"])
        mock_alert.assert_called_once()

    def test_skip_when_position_already_open(self):
        """Caso 3: Omitir despacho si ya hay posición abierta en la misma dirección"""
        self.mock_sb.table().select().eq().eq().execute.return_value.data = [
            {"id": "pos_1", "symbol": "NVDA", "direction": "bullish", "status": "open"}
        ]

        cand = {"ticker": "NVDA", "price": 150.0}
        res = dispatch_autonomous_option_trade(cand, direction="CALL", supabase=self.mock_sb)

        self.assertFalse(res["success"])
        self.assertIn("ya abierta", res["reason"])

    def test_skip_when_order_in_flight(self):
        """Caso 4: Omitir despacho si ya hay una orden en vuelo pendiente para este ticker"""
        self.mock_sb.table().select().eq().eq().execute.return_value.data = []
        self.mock_sb.table().select().like().in_().execute.return_value.data = [
            {"id": "ord_pending_1", "status": "pending", "ticker": "SPY:OPT:20261106:765:C"}
        ]

        cand = {"ticker": "SPY", "price": 765.0}
        res = dispatch_autonomous_option_trade(cand, direction="CALL", supabase=self.mock_sb)

        self.assertFalse(res["success"])
        self.assertIn("en vuelo", res["reason"])

    @patch("app.options.autonomous_options_dispatcher.fetch_and_select_best_option_contract")
    def test_no_contract_found(self, mock_picker):
        """Caso 5: Manejo robusto si no hay contratos que cumplan liquidez o DTE"""
        mock_picker.return_value = (None, ["Sin liquidez suficiente en strikes ATM"])

        cand = {"ticker": "XYZ", "price": 10.0}
        res = dispatch_autonomous_option_trade(cand, direction="CALL", supabase=self.mock_sb)

        self.assertFalse(res["success"])
        self.assertIn("Sin contratos", res["reason"])


if __name__ == "__main__":
    unittest.main()
