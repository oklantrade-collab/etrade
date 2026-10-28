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
from app.options.intraday_momentum_options_scanner import (
    evaluate_intraday_momentum_breakout,
    is_institutional_golden_window,
    evaluate_options_universe_eligibility,
    is_symbol_protected_by_win,
    evaluate_options_catalyst_status,
    CORE_MOMENTUM_OPTION_SYMBOLS
)
from app.options.autonomous_options_dispatcher import dispatch_autonomous_option_trade


class TestIntradayMomentumOptions(unittest.TestCase):

    def setUp(self):
        self.today = date.today()
        self.gate_patcher = patch("app.options.aduana_gap_runner_options.fetch_and_evaluate_options_gatekeeper", return_value={"approved": True, "stage": "ALL", "reason": "Mocked"})
        self.gate_patcher.start()

    def tearDown(self):
        self.gate_patcher.stop()

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


    def test_gamma_ignition_tp1_and_tp2_exits(self):
        """Valida que evaluate_options_gap_aduana_exit ejecute TP1 (+50%) y TP2 (+100%)."""
        from app.options.aduana_gap_runner_options import evaluate_options_gap_aduana_exit

        pos = {
            "symbol": "AMD",
            "direction": "CALL",
            "avg_price": 2.00,
            "entry_debit": 2.00,
            "selection_mode": "OTM_MOMENTUM",
            "tp1_executed": False
        }

        # 1. Ganancia +55% (Supera TP1 de +50%)
        res_tp1 = evaluate_options_gap_aduana_exit(
            position=pos,
            current_underlying_price=105.0,
            current_option_premium=3.10
        )
        self.assertTrue(res_tp1["should_exit"])
        self.assertEqual(res_tp1["exit_type"], "take_profit_partial")
        self.assertEqual(res_tp1["contracts_ratio_to_exit"], 0.50)
        self.assertEqual(res_tp1["rule_code"], "OPT_TP1_50PCT")

        # 2. Ganancia +110% tras TP1 (Supera TP2 de +100%)
        pos_after_tp1 = dict(pos, tp1_executed=True, tp2_executed=False)
        res_tp2 = evaluate_options_gap_aduana_exit(
            position=pos_after_tp1,
            current_underlying_price=110.0,
            current_option_premium=4.20
        )
        self.assertTrue(res_tp2["should_exit"])
        self.assertEqual(res_tp2["exit_type"], "take_profit_partial")
        self.assertEqual(res_tp2["contracts_ratio_to_exit"], 0.60)
        self.assertEqual(res_tp2["rule_code"], "OPT_TP2_100PCT")

    def test_gamma_ignition_call_1h_ema3_flat_or_down_exhaustion_exit(self):
        """Valida que en CALL si la EMA3 1H se frena o declina, se liquide la posición por agotamiento macro."""
        from app.options.aduana_gap_runner_options import evaluate_options_gap_aduana_exit

        pos = {
            "symbol": "AMD",
            "direction": "CALL",
            "avg_price": 2.00,
            "selection_mode": "OTM_MOMENTUM"
        }

        # 1H donde la vela actual retrocede (close baja de 105 a 103), provocando que EMA3 baje
        df_1h_declining = pd.DataFrame({
            "open": [98.0, 100.0, 102.0, 104.0, 105.0, 104.0],
            "high": [100.0, 102.0, 104.0, 106.0, 106.0, 104.5],
            "low": [97.5, 99.5, 101.5, 103.5, 103.0, 102.5],
            "close": [99.5, 101.8, 103.8, 105.5, 104.8, 103.0], # Bajando al final
            "volume": [500_000 for _ in range(6)]
        })

        res = evaluate_options_gap_aduana_exit(
            position=pos,
            current_underlying_price=103.0,
            current_option_premium=2.10,
            df_1h=df_1h_declining,
            position_age_minutes=15.0
        )

        self.assertTrue(res["should_exit"])
        self.assertEqual(res["exit_type"], "exhaustion_exit")
        self.assertEqual(res["contracts_ratio_to_exit"], 1.0)
        self.assertEqual(res["rule_code"], "OPT_MOMENTUM_1H_EMA3_EXHAUSTION")

    def test_gamma_ignition_call_15m_ema3_crosses_below_ema9_exit(self):
        """Valida que en CALL si EMA3 15m < EMA9 15m, se liquide la posición por giro táctico."""
        from app.options.aduana_gap_runner_options import evaluate_options_gap_aduana_exit

        pos = {
            "symbol": "AMD",
            "direction": "CALL",
            "avg_price": 2.00,
            "selection_mode": "OTM_MOMENTUM"
        }

        # 1H alcista fuerte
        df_1h_bullish = pd.DataFrame({
            "close": [95.0, 97.0, 99.0, 101.0, 103.0, 105.0]
        })

        # 15m con giro bajista reciente donde EMA3 < EMA9
        # (ej. caídas sucesivas al final: 105, 104, 103.2, 102.5, 101.8)
        c15_series = [98.0, 99.0, 100.0, 102.0, 104.0, 105.0, 103.0, 101.5, 99.5, 98.0]
        df_15m_bear_cross = pd.DataFrame({
            "close": c15_series
        })

        res = evaluate_options_gap_aduana_exit(
            position=pos,
            current_underlying_price=101.0,
            current_option_premium=2.05,
            df_1h=df_1h_bullish,
            df_15m=df_15m_bear_cross,
            position_age_minutes=15.0
        )

        self.assertTrue(res["should_exit"])
        self.assertEqual(res["exit_type"], "exhaustion_exit")
        self.assertEqual(res["contracts_ratio_to_exit"], 1.0)
        self.assertEqual(res["rule_code"], "OPT_MOMENTUM_15M_EMA3_LE_EMA9")

    def test_gamma_ignition_put_exhaustion_and_crossover_exits(self):
        """Valida salidas a la inversa para PUTs (1H EMA3 sube o 15m EMA3 > EMA9)."""
        from app.options.aduana_gap_runner_options import evaluate_options_gap_aduana_exit

        pos = {
            "symbol": "TSLA",
            "direction": "PUT",
            "avg_price": 2.50,
            "selection_mode": "OTM_MOMENTUM"
        }

        # 1. 1H EMA3 deja de bajar y asciende (rebote alcista contra el PUT)
        df_1h_bouncing = pd.DataFrame({
            "close": [110.0, 108.0, 105.0, 102.0, 103.5, 105.0] # Rebote al final
        })

        res_put_1h = evaluate_options_gap_aduana_exit(
            position=pos,
            current_underlying_price=105.0,
            current_option_premium=2.30,
            df_1h=df_1h_bouncing,
            position_age_minutes=15.0
        )
        self.assertTrue(res_put_1h["should_exit"])
        self.assertEqual(res_put_1h["rule_code"], "OPT_MOMENTUM_1H_EMA3_EXHAUSTION")

        # 2. 15m EMA3 cruza por encima de EMA9 en PUT
        df_1h_bear = pd.DataFrame({"close": [115.0, 112.0, 109.0, 106.0, 103.0, 100.0]})
        c15_bounce = [105.0, 103.0, 101.0, 99.0, 98.0, 97.0, 98.5, 99.5, 100.5, 101.5]
        df_15m_bull_cross = pd.DataFrame({"close": c15_bounce})

        res_put_15m = evaluate_options_gap_aduana_exit(
            position=pos,
            current_underlying_price=101.5,
            current_option_premium=2.20,
            df_1h=df_1h_bear,
            df_15m=df_15m_bull_cross,
            position_age_minutes=15.0
        )
        self.assertTrue(res_put_15m["should_exit"])
        self.assertEqual(res_put_15m["rule_code"], "OPT_MOMENTUM_15M_EMA3_GE_EMA9")



    def test_is_institutional_golden_window(self):
        """Valida la Ventana de Oro Institucional (09:45 a 11:45 ET)."""
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        # 10:15 ET (Dentro de ventana)
        dt_in = datetime(2026, 10, 27, 10, 15, tzinfo=ZoneInfo("America/New_York"))
        is_ok, msg = is_institutional_golden_window(dt_in)
        self.assertTrue(is_ok)
        self.assertIn("activa", msg)

        # 09:35 ET (Antes de 09:45 ET)
        dt_pre = datetime(2026, 10, 27, 9, 35, tzinfo=ZoneInfo("America/New_York"))
        is_ok_pre, msg_pre = is_institutional_golden_window(dt_pre)
        self.assertFalse(is_ok_pre)
        self.assertIn("09:45 ET", msg_pre)

        # 12:30 ET (Bloqueo de mediodía)
        dt_lunch = datetime(2026, 10, 27, 12, 30, tzinfo=ZoneInfo("America/New_York"))
        is_ok_lunch, msg_lunch = is_institutional_golden_window(dt_lunch)
        self.assertFalse(is_ok_lunch)
        self.assertIn("11:45 ET", msg_lunch)

    def test_evaluate_options_universe_eligibility(self):
        """Valida reglas cuantitativas de exclusión de universo."""
        # Miembros de la Canasta Élite aprobados
        self.assertTrue(evaluate_options_universe_eligibility("AMD")[0])
        self.assertTrue(evaluate_options_universe_eligibility("AAPL")[0])
        self.assertTrue(evaluate_options_universe_eligibility("NVDA")[0])

        # Exclusiones automáticas comprobadas
        is_spy, msg_spy = evaluate_options_universe_eligibility("SPY")
        self.assertFalse(is_spy)
        self.assertIn("Excluido", msg_spy)

        is_mara, msg_mara = evaluate_options_universe_eligibility("MARA")
        self.assertFalse(is_mara)

        is_msft, msg_msft = evaluate_options_universe_eligibility("MSFT")
        self.assertFalse(is_msft)

        # Símbolo custom con Beta < 1.35 rechazado
        is_slow, msg_slow = evaluate_options_universe_eligibility("XYZ", beta=1.10, adr_pct=3.0, spread_pct=2.0, price=50.0)
        self.assertFalse(is_slow)
        self.assertIn("Beta insuficiente", msg_slow)

        # Símbolo custom con Spread > 3.5% rechazado
        is_wide, msg_wide = evaluate_options_universe_eligibility("ABC", beta=1.50, adr_pct=3.5, spread_pct=4.2, price=60.0)
        self.assertFalse(is_wide)
        self.assertIn("Spread", msg_wide)

    @patch("app.core.supabase_client.get_supabase")
    def test_protect_the_win_locks_symbol_with_prior_gain(self, mock_get_sb):
        """Valida regla 'Protect the Win': 1 ganador y candado para el resto del día."""
        mock_sb = MagicMock()
        mock_get_sb.return_value = mock_sb

        # Caso A: Activo ya cerró trade hoy con +25% de ganancia -> Bloqueado
        mock_sb.table().select().eq().eq().gte().execute.return_value = MagicMock(data=[
            {"id": "opt-1", "symbol": "AMD", "pnl_pct": 25.0, "realized_pnl": 500.0}
        ])
        is_prot, msg = is_symbol_protected_by_win("AMD", mock_sb)
        self.assertTrue(is_prot)
        self.assertIn("Protect the Win", msg)

        # Caso B: Activo sin trades cerrados hoy -> Permitido
        mock_sb.table().select().eq().eq().gte().execute.return_value = MagicMock(data=[])
        is_prot_b, _ = is_symbol_protected_by_win("NVDA", mock_sb)
        self.assertFalse(is_prot_b)

    @patch("app.stocks.news_catalyst_service.get_news_catalyst")
    def test_evaluate_options_catalyst_status(self, mock_news):
        """Valida bloqueo anti-earnings (IV Crush) y bonificación post-earnings/noticias."""
        # 1. Bloqueo anti-earnings si reporta hoy After-Hours
        mock_news.return_value = {
            "has_earnings_event": True,
            "earnings_timing": "today_after_market",
            "tier": "tier_2",
            "headline": "Reports Q3 Earnings Today After Market Close"
        }
        res_blocked = evaluate_options_catalyst_status("NVDA")
        self.assertTrue(res_blocked["is_blocked"])
        self.assertIn("IV Crush", res_blocked["block_reason"])

        # 2. Bonificación post-earnings si reportó ayer en la tarde (día de reacción)
        mock_news.return_value = {
            "has_earnings_event": True,
            "earnings_timing": "yesterday_after_market",
            "tier": "tier_2",
            "headline": "Q3 Revenue Beat by 15%, Guidance Raised"
        }
        res_reaction = evaluate_options_catalyst_status("AMD")
        self.assertFalse(res_reaction["is_blocked"])
        self.assertEqual(res_reaction["score_bonus"], 20.0)
        self.assertEqual(res_reaction["catalyst_tag"], "POST_EARNINGS_MOMENTUM")

        # 3. Noticia Tier 1 (FDA / Gran Contrato)
        mock_news.return_value = {
            "has_earnings_event": False,
            "tier": "tier_1",
            "category": "Contrato Mayor",
            "headline": "Awarded Pentagon AI Deal"
        }
        res_tier1 = evaluate_options_catalyst_status("PLTR")
        self.assertFalse(res_tier1["is_blocked"])
        self.assertEqual(res_tier1["score_bonus"], 20.0)
        self.assertIn("TIER_1_NEWS", res_tier1["catalyst_tag"])

    def test_calibrated_be_lock_requires_12pct_peak(self):
        """Valida que en modo OTM_MOMENTUM el Breakeven Lock exija avance >= +12% de prima."""
        from app.options.aduana_gap_runner_options import evaluate_options_gap_aduana_exit

        pos = {
            "symbol": "AMD",
            "direction": "CALL",
            "avg_price": 2.00,
            "entry_underlying_price": 100.0,
            "selection_mode": "OTM_MOMENTUM",
            "rule_code": "GAMMA_IGNITION_OTM_ITM"
        }

        # Caso A: Pico fue solo +7% (ruido normal de spread). No debe disparar BE Lock
        pos["highest_premium_seen"] = 2.14 # +7.0% pico
        res_a = evaluate_options_gap_aduana_exit(
            position=pos,
            current_underlying_price=100.2,
            current_option_premium=2.01,
            position_age_minutes=5.0
        )
        self.assertFalse(res_a["should_exit"])

        # Caso B: Pico superó +13% (avance institucional real) y retrocede a compra + 1% ($2.02)
        pos["highest_premium_seen"] = 2.28 # +14.0% pico
        res_b = evaluate_options_gap_aduana_exit(
            position=pos,
            current_underlying_price=100.3,
            current_option_premium=2.02,
            position_age_minutes=10.0
        )
        self.assertTrue(res_b["should_exit"])
        self.assertEqual(res_b["rule_code"], "OPT_GAP_BE_LOCK_PLUS_1PCT")

    def test_opt_contract_picker_enforces_strict_spread_in_otm_momentum(self):
        """Valida que en OTM_MOMENTUM se aplique spread estricto <= 3.5%."""
        exp = self.today + timedelta(days=3)
        contracts = [
            # Contrato con spread del 5.0% ($2.00 / $2.10, mid $2.05) -> Rechazado en OTM
            {
                "contract_id": 301, "conid": 301, "symbol": "NVDA", "right": "C",
                "strike": 103.0, "expiry": exp.isoformat(), "bid": 2.00, "ask": 2.10,
                "delta": 0.35, "open_interest": 3000, "volume": 1500
            },
            # Contrato con spread del 2.0% ($2.00 / $2.04, mid $2.02) -> Aprobado
            {
                "contract_id": 302, "conid": 302, "symbol": "NVDA", "right": "C",
                "strike": 103.0, "expiry": exp.isoformat(), "bid": 2.00, "ask": 2.04,
                "delta": 0.35, "open_interest": 4000, "volume": 2500
            }
        ]

        # Con el spread del 5%, es rechazado
        best_wide, rej_wide = select_best_option_contract(
            contracts=[contracts[0]],
            underlying_price=100.0,
            direction="CALL",
            selection_mode="OTM_MOMENTUM",
            now_date=self.today
        )
        self.assertIsNone(best_wide)
        self.assertTrue(any("Spread excesivo" in r for r in rej_wide))

        # Con el spread del 2%, es aprobado
        best_tight, _ = select_best_option_contract(
            contracts=[contracts[1]],
            underlying_price=100.0,
            direction="CALL",
            selection_mode="OTM_MOMENTUM",
            now_date=self.today
        )
        self.assertIsNotNone(best_tight)


if __name__ == "__main__":
    unittest.main()
