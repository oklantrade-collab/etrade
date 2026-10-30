"""Tests del Velocity Score y ranking por velocidad (módulo puro)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.stocks import velocity_ranking as vr
from app.stocks.velocity_ranking import (
    compute_velocity_score,
    parse_velocity_config,
    passes_velocity_minimums,
    rank_by_velocity,
    get_recorded_velocity,
)


def _item(ticker="AAA", **kw):
    base = {
        "ticker": ticker, "rvol": 5.0, "adx_5m": 35.0, "plus_di_5m": 30.0, "minus_di_5m": 10.0,
        "delta_p_5m_pct": 2.0, "volume": 5_000_000, "change_pct": 12.0, "is_ema3_above_ema9_5m": True,
    }
    base.update(kw)
    return base


class TestVelocityConfig(unittest.TestCase):
    def test_defaults_and_weights_sum_to_one(self):
        cfg = parse_velocity_config(None)
        total = cfg["velocity_w_rvol"] + cfg["velocity_w_adx"] + cfg["velocity_w_dp5m"] + cfg["velocity_w_vol"]
        self.assertAlmostEqual(total, 1.0, places=6)
        self.assertEqual(cfg["scanner_refresh_seconds"], 60.0)

    def test_weights_renormalized_and_string_values(self):
        cfg = parse_velocity_config({
            "velocity_w_rvol": "2", "velocity_w_adx": "2", "velocity_w_dp5m": "0", "velocity_w_vol": "0",
            "scanner_min_rvol": "2.5",
        })
        self.assertAlmostEqual(cfg["velocity_w_rvol"], 0.5)
        self.assertAlmostEqual(cfg["velocity_w_adx"], 0.5)
        self.assertEqual(cfg["scanner_min_rvol"], 2.5)

    def test_invalid_values_fallback_to_defaults_and_min_refresh(self):
        cfg = parse_velocity_config({"scanner_min_rvol": "abc", "scanner_refresh_seconds": "1"})
        self.assertEqual(cfg["scanner_min_rvol"], 1.5)
        self.assertEqual(cfg["scanner_refresh_seconds"], 15.0)


class TestVelocityScore(unittest.TestCase):
    def test_fast_beats_slow(self):
        fast = compute_velocity_score(_item())
        slow = compute_velocity_score(_item(rvol=1.2, adx_5m=16, delta_p_5m_pct=0.1, volume=400_000))
        self.assertGreater(fast.score, slow.score + 30)

    def test_adverse_di_penalizes_adx(self):
        bull = compute_velocity_score(_item(plus_di_5m=30, minus_di_5m=10))
        bear = compute_velocity_score(_item(plus_di_5m=10, minus_di_5m=30))
        self.assertGreater(bull.score, bear.score)
        self.assertEqual(bear.components["dir_factor"], vr.ADX_ADVERSE_DI_FACTOR)

    def test_score_bounded_0_100(self):
        top = compute_velocity_score(_item(rvol=500, adx_5m=99, delta_p_5m_pct=50, volume=10**10))
        zero = compute_velocity_score({})
        self.assertLessEqual(top.score, 100.0)
        self.assertGreaterEqual(zero.score, 0.0)

    def test_descending_requires_negative_dp5m_and_bearish_5m_ema(self):
        self.assertTrue(compute_velocity_score(_item(delta_p_5m_pct=-0.8, is_ema3_above_ema9_5m=False)).is_descending)
        self.assertFalse(compute_velocity_score(_item(delta_p_5m_pct=-0.8, is_ema3_above_ema9_5m=True)).is_descending)
        self.assertFalse(compute_velocity_score(_item(delta_p_5m_pct=1.0, is_ema3_above_ema9_5m=False)).is_descending)

    def test_nan_and_none_are_safe(self):
        r = compute_velocity_score({"rvol": float("nan"), "adx_5m": None, "volume": "N/A"})
        self.assertGreaterEqual(r.score, 0.0)


class TestMinimumsAndRanking(unittest.TestCase):
    def test_minimums_reject_reasons(self):
        cfg = parse_velocity_config(None)
        self.assertTrue(passes_velocity_minimums(_item(), cfg)[0])
        self.assertIn("change", passes_velocity_minimums(_item(change_pct=1.0), cfg)[1])
        self.assertIn("rvol", passes_velocity_minimums(_item(rvol=1.0), cfg)[1])
        self.assertIn("volume", passes_velocity_minimums(_item(volume=1000), cfg)[1])
        self.assertIn("adx", passes_velocity_minimums(_item(adx_5m=10), cfg)[1])

    def test_minimums_follow_config(self):
        strict = parse_velocity_config({"scanner_min_change_pct": "20"})
        self.assertFalse(passes_velocity_minimums(_item(change_pct=12.0), strict)[0])

    def test_rank_orders_desc_and_drops_descending_and_below_minimums(self):
        items = [
            _item("SLOW", rvol=1.6, adx_5m=21, delta_p_5m_pct=0.2, volume=350_000),
            _item("FAST", rvol=8.0, adx_5m=45, delta_p_5m_pct=3.5, volume=20_000_000),
            _item("DESC", delta_p_5m_pct=-1.0, is_ema3_above_ema9_5m=False),
            _item("TINY", change_pct=0.5),
            _item("MID", rvol=3.0, adx_5m=28, delta_p_5m_pct=1.0, volume=2_000_000),
        ]
        out = rank_by_velocity(items)
        self.assertEqual([i["ticker"] for i in out], ["FAST", "MID", "SLOW"])
        self.assertTrue(all("velocity_score" in i for i in out))

    def test_penalized_go_last_or_are_removed(self):
        items = [_item("BLK", status="blocked", rvol=9, adx_5m=48), _item("OK", rvol=3.0, adx_5m=25)]
        out = rank_by_velocity(items)
        self.assertEqual([i["ticker"] for i in out], ["OK", "BLK"])
        out2 = rank_by_velocity([dict(i) for i in items], keep_penalized=False)
        self.assertEqual([i["ticker"] for i in out2], ["OK"])

    def test_gap_runner_flag_does_not_change_order(self):
        items = [_item("GAP", is_gap_runner=True, rvol=1.6, adx_5m=21, delta_p_5m_pct=0.1),
                 _item("RIP", rvol=7, adx_5m=40, delta_p_5m_pct=3)]
        out = rank_by_velocity(items)
        self.assertEqual(out[0]["ticker"], "RIP")

    def test_registry_records_latest_velocity(self):
        rank_by_velocity([_item("REGX")])
        rec = get_recorded_velocity("REGX")
        self.assertIsNotNone(rec)
        self.assertGreater(rec["velocity_score"], 0)
        self.assertIsNone(get_recorded_velocity("NOPE_NOT_RECORDED"))


if __name__ == "__main__":
    unittest.main()
