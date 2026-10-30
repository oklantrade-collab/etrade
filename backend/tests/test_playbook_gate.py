"""Tests del gate Playbook/Velocidad previo al disparo y su integración con el MicroPullbackEngine."""
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.stocks import playbook_gate as pg
from app.stocks.playbook_gate import GateDecision, evaluate_entry_gate, detect_flat_top, has_topping_tail
from app.stocks.micro_pullback_engine import MicroPullbackEngine, ScalpCandidateState

MONDAY = datetime(2026, 10, 26, 10, 0)
FRIDAY = datetime(2026, 10, 30, 10, 0)


def _bars(n=10, price=5.0):
    return [{"open": price, "high": price + 0.05, "low": price - 0.05, "close": price,
             "upper_wick_ratio": 0.1, "lower_wick_ratio": 0.1, "is_green": True} for _ in range(n)]


def _cfg(mode="enforce", min_score=10.0):
    return {"playbook_gate_mode": mode, "velocity_gate_min_score": min_score, "cold_market_spy_pct": -0.3}


class TestDetectors(unittest.TestCase):
    def test_topping_tail(self):
        b = _bars(3)
        self.assertFalse(has_topping_tail(b))
        b[-1]["upper_wick_ratio"] = 0.55
        self.assertTrue(has_topping_tail(b))

    def test_flat_top(self):
        flat = [{"high": 7.33, "close": 7.32} for _ in range(10)]
        self.assertTrue(detect_flat_top(flat))
        rising = [{"high": 5.0 + i * 0.1, "close": 5.0 + i * 0.1} for i in range(10)]
        self.assertFalse(detect_flat_top(rising))


class TestEvaluateEntryGate(unittest.TestCase):
    def _run(self, cold=False, mode="enforce", vel=None, bars=None, now=MONDAY, rule="SCALP_MICRO_PULLBACK", snap=None):
        with patch.object(pg, "load_gate_config_cached", return_value=_cfg(mode)), \
             patch.object(pg, "is_cold_market", return_value=cold), \
             patch.object(pg, "get_recorded_velocity", return_value=vel):
            return evaluate_entry_gate("TST", 5.0, bars or _bars(), rule_code=rule, snap=snap or {}, now=now)

    def test_normal_market_allows_full_size(self):
        d = self._run(vel={"velocity_score": 55.0, "change_pct": 20.0, "volume": 3_000_000})
        self.assertTrue(d.allow)
        self.assertEqual(d.size_multiplier, 1.0)

    def test_low_velocity_blocks_in_enforce(self):
        d = self._run(vel={"velocity_score": 3.0})
        self.assertFalse(d.allow)
        self.assertEqual(d.action, "BLOCK_LOW_VELOCITY")

    def test_no_velocity_record_fails_open(self):
        d = self._run(vel=None)
        self.assertTrue(d.allow)

    def test_cold_market_reduces_size_to_30pct(self):
        d = self._run(cold=True, vel={"velocity_score": 60.0, "change_pct": 10.0})
        self.assertTrue(d.allow)
        self.assertAlmostEqual(d.size_multiplier, 0.30)
        self.assertTrue(d.market_cold)

    def test_cold_market_friday_uses_tenth_size(self):
        d = self._run(cold=True, now=FRIDAY, vel={"velocity_score": 60.0, "change_pct": 10.0})
        self.assertAlmostEqual(d.size_multiplier, 0.10)

    def test_cold_market_topping_tail_blocks(self):
        bars = _bars(5)
        bars[-1]["upper_wick_ratio"] = 0.6
        d = self._run(cold=True, bars=bars, vel={"velocity_score": 60.0, "change_pct": 10.0})
        self.assertFalse(d.allow)
        self.assertEqual(d.action, "DEFENSIVE_CUT_TOPPING_TAIL")

    def test_cold_market_flat_top_blocks(self):
        flat = [{"open": 7.3, "high": 7.33, "low": 7.28, "close": 7.32, "upper_wick_ratio": 0.1} for _ in range(12)]
        d = self._run(cold=True, bars=flat, vel={"velocity_score": 60.0, "change_pct": 10.0})
        self.assertFalse(d.allow)
        self.assertEqual(d.action, "BLOCK_FLAT_TOP_BREAKOUT_IN_COLD_MARKET")

    def test_flat_top_allowed_in_normal_market(self):
        flat = [{"open": 7.3, "high": 7.33, "low": 7.28, "close": 7.32, "upper_wick_ratio": 0.1} for _ in range(12)]
        d = self._run(cold=False, bars=flat, vel={"velocity_score": 60.0, "change_pct": 10.0})
        self.assertTrue(d.allow)

    def test_negative_macd_blocks_initial_entry_but_not_dip(self):
        snap = {"macd_hist_5m": -0.02}
        init = self._run(snap=snap, vel={"velocity_score": 60.0, "change_pct": 40.0})
        self.assertFalse(init.allow)
        self.assertEqual(init.action, "BLOCK_NEGATIVE_MACD_MOMENTUM")
        dip = self._run(snap=snap, rule="SCALP_BUY_THE_DIP", vel={"velocity_score": 60.0, "change_pct": 40.0})
        self.assertTrue(dip.allow)

    def test_observe_mode_never_blocks_nor_resizes(self):
        d = self._run(cold=True, mode="observe", vel={"velocity_score": 1.0})
        self.assertTrue(d.allow)
        self.assertEqual(d.size_multiplier, 1.0)
        self.assertTrue(d.would_block)

    def test_playbook_exception_fails_open(self):
        with patch.object(pg, "load_gate_config_cached", return_value=_cfg()), \
             patch.object(pg, "is_cold_market", side_effect=RuntimeError("boom")):
            d = evaluate_entry_gate("TST", 5.0, _bars(), now=MONDAY)
        self.assertTrue(d.allow)


class TestEngineIntegration(unittest.TestCase):
    def setUp(self):
        self.engine = MicroPullbackEngine()
        self.engine.daily_cushion_usd = 0.0
        self.cand = ScalpCandidateState("TST")
        self.cand.pullback_low = 4.90
        self.cand.impulse_high = 5.50
        self.cand.impulse_low = 4.50
        self.engine.candidates["TST"] = self.cand
        for b in _bars(3):
            self.cand.bars.append(b)

    def _ib(self):
        conn = MagicMock()
        conn.connected = True
        conn.get_next_order_id.return_value = 1
        conn.us_stock_contract.return_value = MagicMock()
        return conn

    def test_blocked_gate_prevents_order_and_resets_phase(self):
        blocked = GateDecision(allow=False, action="BLOCK_FLAT_TOP_BREAKOUT_IN_COLD_MARKET", reasoning="x")
        conn = self._ib()
        with patch.object(MicroPullbackEngine, "_run_entry_gate", return_value=blocked), \
             patch("app.stocks.micro_pullback_engine.get_ib_connection", return_value=conn):
            self.cand.phase = "PULLBACK_OBSERVED"
            self.engine._trigger_entry(self.cand, entry_price=5.0)
        conn.placeOrder.assert_not_called()
        self.assertEqual(self.cand.phase, "IDLE")
        self.assertFalse(self.cand.in_trade)

    def test_blocked_dip_keeps_waiting_and_restores_rebuy_counter(self):
        blocked = GateDecision(allow=False, action="BLOCK_LOW_VELOCITY", reasoning="x")
        self.cand.phase = "WAITING_DIP_5M"
        self.cand.rebuys_count = 1
        with patch.object(MicroPullbackEngine, "_run_entry_gate", return_value=blocked), \
             patch("app.stocks.micro_pullback_engine.get_ib_connection", return_value=self._ib()):
            self.engine._trigger_entry(self.cand, entry_price=5.0, rule_code="SCALP_BUY_THE_DIP")
        self.assertEqual(self.cand.phase, "WAITING_DIP_5M")
        self.assertEqual(self.cand.rebuys_count, 0)

    def test_size_multiplier_and_tight_stop_are_applied(self):
        gate = GateDecision(allow=True, size_multiplier=0.30, fixed_stop_cents=0.15, action="USE_TIGHT_MICRO_STOP_10_CENTS")
        self.cand.pullback_low = 4.50  # soporte lejano (10% abajo): el stop estructural sería 4.48
        conn = self._ib()
        with patch.object(MicroPullbackEngine, "_run_entry_gate", return_value=gate), \
             patch.object(MicroPullbackEngine, "_calculate_scalp_shares", return_value=40) as mock_sh, \
             patch.object(MicroPullbackEngine, "_safe_create_task"), \
             patch("app.stocks.micro_pullback_engine.get_ib_connection", return_value=conn):
            self.engine._trigger_entry(self.cand, entry_price=5.0)
        mock_sh.assert_called_once_with(5.0, size_multiplier=0.30)
        self.assertTrue(self.cand.in_trade)
        self.assertAlmostEqual(self.cand.stop_loss, 4.85)  # 5.00 - 0.15 (stop ceñido MNDR)

    def test_allowed_gate_sends_order(self):
        conn = self._ib()
        with patch.object(MicroPullbackEngine, "_run_entry_gate", return_value=GateDecision()), \
             patch.object(MicroPullbackEngine, "_calculate_scalp_shares", return_value=40), \
             patch.object(MicroPullbackEngine, "_safe_create_task"), \
             patch("app.stocks.micro_pullback_engine.get_ib_connection", return_value=conn):
            self.engine._trigger_entry(self.cand, entry_price=5.0)
        conn.placeOrder.assert_called_once()
        self.assertTrue(self.cand.in_trade)


if __name__ == "__main__":
    unittest.main()
