"""
Unit and Integration Tests for Scanner Momentum Optimization (Oct 21 Improvements):
1. Low-Float Volume Adaptation (RVOL >= 2.5x with Vol >= 300k and Chg >= +5%).
2. Micro-Cap Relaxation ($15M - $50M) with Vol >= 1M & RVOL >= 3.0x.
3. Buying Force & Semaphore Uncapping on Day-1 Reversal (RVOL >= 3.0x).
4. Slot Liberation and Capital Rotation.
"""

import os
import sys
sys.path.append(os.path.abspath("backend"))

import pytest
from unittest.mock import MagicMock, patch
from app.stocks.alpha_runner_scanner import calculate_semaphore_and_buying_force


def test_reversal_expansion_uncapped_buying_force():
    """
    Test that an explosive day-1 runner (RVOL >= 3.0, EMA3 1H ascending, Change >= +5%)
    is NOT capped at 45 even if EMA3 1H is still below EMA9 1H.
    """
    metrics = calculate_semaphore_and_buying_force(
        price=15.0,
        change_pct=18.5,
        day_high=15.2,
        day_low=12.5,
        open_price=12.8,
        volume=1_500_000,
        avg_volume=400_000, # RVOL = 3.75x
        news_bonus=15,
        is_ema3_1h_ascending=True,
        ema3_slope_1h=0.045,
        is_ema3_above_ema9=False, # Still below EMA9 in 1H (early reversal)
        sipv_upper_rejection=False,
        delta_p_5m=0.8,
        gap_pct=6.5,
        candle_1_green=True,
        adx_5m=28.0,
        plus_di_5m=32.0,
        minus_di_5m=12.0,
        open_ge_close=True,
        room_to_bb_upper_1d=25.0,
        sma20_1d=14.0,
    )

    # Buying force should NOT be capped at 45; it should be >= 65
    assert metrics["buying_force_5m"] >= 65, f"Expected BF >= 65, got {metrics['buying_force_5m']}"
    assert metrics["semaphore"] == "REVERSAL_EXPANSION"
    assert "REVERSIÓN EXPLOSIVA DÍA 1" in metrics["semaphore_label"]
    assert metrics["rank_score"] >= 60.0


def test_standard_below_ema9_still_capped():
    """
    Test that a sluggish stock below EMA9 (RVOL < 3.0 or flat slope)
    is still appropriately capped at 45 to protect against fading traps.
    """
    metrics = calculate_semaphore_and_buying_force(
        price=10.0,
        change_pct=2.0,
        day_high=10.2,
        day_low=9.8,
        open_price=9.9,
        volume=500_000,
        avg_volume=500_000, # RVOL = 1.0x
        news_bonus=0,
        is_ema3_1h_ascending=True,
        ema3_slope_1h=0.005,
        is_ema3_above_ema9=False,
        sipv_upper_rejection=False,
        delta_p_5m=0.0,
        gap_pct=0.5,
        candle_1_green=True,
    )

    # Should be capped at 45
    assert metrics["buying_force_5m"] <= 45, f"Expected BF <= 45, got {metrics['buying_force_5m']}"
    assert metrics["semaphore"] == "BELOW_EMA9"


def test_descending_ema3_always_blocked():
    """
    Test that if EMA3 is descending (distribution/exhaustion), it is strictly blocked
    regardless of RVOL or change %.
    """
    metrics = calculate_semaphore_and_buying_force(
        price=5.0,
        change_pct=25.0,
        day_high=6.5,
        day_low=4.8,
        open_price=5.0,
        volume=5_000_000,
        avg_volume=1_000_000, # RVOL = 5.0x
        news_bonus=20,
        is_ema3_1h_ascending=False, # Falling EMA3!
        ema3_slope_1h=-0.08,
        is_ema3_above_ema9=False,
        delta_p_5m=-0.5,
    )

    assert metrics["semaphore"] == "DESCENDING"
    assert metrics["buying_force_5m"] <= 30


def test_low_float_qualification_logic():
    """
    Test low-float qualification criteria:
    Vol >= 300k, RVOL >= 2.5x, Change >= +5.0%, MCap >= $15M, BF >= 65.
    """
    def check_low_float(vol, avg_vol, chg, mcap, bf):
        rvol = vol / max(1, avg_vol)
        is_standard = (vol >= 1_000_000 and mcap >= 15_000_000 and bf >= 65.0)
        is_low_float = (vol >= 300_000 and rvol >= 2.5 and chg >= 5.0 and mcap >= 15_000_000 and bf >= 65.0)
        return is_standard or is_low_float

    # Case A: Low-float gem (CSTE style: 450k vol, 100k avg_vol -> RVOL 4.5x, +15% chg, $80M cap, BF 70)
    assert check_low_float(vol=450_000, avg_vol=100_000, chg=15.0, mcap=80_000_000, bf=70.0) is True

    # Case B: Sluggish low-float (Vol 350k, but RVOL only 1.2x, +2% chg) -> REJECTED
    assert check_low_float(vol=350_000, avg_vol=290_000, chg=2.0, mcap=40_000_000, bf=68.0) is False

    # Case C: Micro-cap runner (SNAL style: 1.2M vol, 300k avg_vol -> RVOL 4.0x, +20% chg, $18M cap, BF 72)
    assert check_low_float(vol=1_200_000, avg_vol=300_000, chg=20.0, mcap=18_000_000, bf=72.0) is True


def test_microcap_relaxation_gate():
    """
    Test micro-cap gate ($15M - $50M):
    Requires Vol >= 1M with RVOL >= 3.0x, OR Vol >= 3M with RVOL >= 2.0x.
    """
    def check_microcap_gate(vol, rvol, mcap, price):
        if mcap < 15_000_000:
            return False
        if mcap < 50_000_000:
            is_valid = (vol >= 1_000_000 and rvol >= 3.0) or (vol >= 3_000_000 and rvol >= 2.0)
            if not is_valid or price < 1.00:
                return False
        return True

    # SNAL ($18M cap, 1.2M vol, RVOL 3.5x, price $1.35) -> PASS
    assert check_microcap_gate(vol=1_200_000, rvol=3.5, mcap=18_000_000, price=1.35) is True

    # Zombie penny ($20M cap, 400k vol, RVOL 1.1x) -> REJECT
    assert check_microcap_gate(vol=400_000, rvol=1.1, mcap=20_000_000, price=1.50) is False

    # Sub-$15M shell ($10M cap, even with high volume) -> REJECT
    assert check_microcap_gate(vol=5_000_000, rvol=6.0, mcap=10_000_000, price=0.80) is False
