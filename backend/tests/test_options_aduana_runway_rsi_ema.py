import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd
import pytest

import app.options.aduana_gap_runner_options as opt
from app.options.aduana_gap_runner_options import (
    evaluate_options_daily_runway,
    evaluate_options_rsi_exhaustion,
    evaluate_options_1h_trend,
    evaluate_options_entry_gatekeeper,
    evaluate_options_gap_entry_tranches,
    get_options_runway_threshold,
)


def _df(closes, vol=100_000):
    closes = list(closes)
    return pd.DataFrame({
        "open": [c - 0.02 for c in closes],
        "high": [c + 0.05 for c in closes],
        "low": [c - 0.05 for c in closes],
        "close": closes,
        "volume": [vol] * len(closes),
    })


def _oscillating(n=40, base=100.0):
    return [base + (0.3 if i % 2 else -0.3) for i in range(n)]


def _trend_1h(sign, n=40):
    """Serie 1H con tendencia y retrocesos (RSI moderado, EMA3 alineada con la dirección)."""
    if sign > 0:
        pat = [0.5, -0.3, 0.4, -0.2, 0.3]
    else:
        pat, n = [-0.25, 0.3, -0.2, 0.25, -0.2], 41
    c = [100.0]
    for i in range(n - 1):
        c.append(c[-1] + pat[i % 5])
    return c


class TestDailyRunway:
    def test_thresholds(self):
        assert get_options_runway_threshold("SPY") == 2.5
        assert get_options_runway_threshold("AAPL") == 20.0
        assert get_options_runway_threshold("MARA") == 20.0

    def test_call_base_runway_approved(self):
        r = evaluate_options_daily_runway("MARA", "CALL", 10.0, 12.5, 7.0, rvol=1.0)
        assert r["approved"] and r["mode"] == "BASE" and r["base_runway_pct"] == 25.0

    def test_call_low_runway_low_volume_excluded(self):
        # Caso DOUG: +0.6% de espacio, RVOL bajo
        r = evaluate_options_daily_runway("DOUG", "CALL", 1.60, 1.61, 1.0, rvol=0.11)
        assert not r["approved"] and r["mode"] == "BLOCKED"
        assert "EXCLUIDO" in r["reason"]

    def test_call_low_runway_high_rvol_without_pressure_excluded(self):
        r = evaluate_options_daily_runway("MARA", "CALL", 10.0, 11.5, 7.0, rvol=6.0, pressure_ok=False)
        assert not r["approved"]

    def test_call_volume_ignition_approved(self):
        # base 15% + min(25, 3.5*(6-1)=17.5) = 32.5% >= 20%
        r = evaluate_options_daily_runway("MARA", "CALL", 10.0, 11.5, 7.0, rvol=6.0, pressure_ok=True)
        assert r["approved"] and r["mode"] == "VOLUME_IGNITION"
        assert r["delta_rvol_pp"] == 17.5 and r["projected_runway_pct"] == 32.5

    def test_call_volume_ignition_not_enough(self):
        # base 1% + 3.5*(3-1)=7 -> 8% < 20%
        r = evaluate_options_daily_runway("MARA", "CALL", 10.0, 10.1, 7.0, rvol=3.0, pressure_ok=True)
        assert not r["approved"] and r["mode"] == "BLOCKED"
        assert r["projected_runway_pct"] == 8.0

    def test_delta_capped_at_25pp(self):
        r = evaluate_options_daily_runway("MARA", "CALL", 10.0, 10.0, 7.0, rvol=50.0, pressure_ok=True)
        assert r["delta_rvol_pp"] == 25.0 and r["approved"]

    def test_put_uses_lower_band(self):
        r = evaluate_options_daily_runway("MARA", "PUT", 10.0, 14.0, 7.0, rvol=1.0)
        assert r["approved"] and r["base_runway_pct"] == 30.0
        r2 = evaluate_options_daily_runway("MARA", "PUT", 10.0, 14.0, 9.8, rvol=1.0)
        assert not r2["approved"]

    def test_etf_uses_small_threshold(self):
        r = evaluate_options_daily_runway("SPY", "CALL", 500.0, 515.0, 480.0, rvol=1.0)
        assert r["approved"]  # +3.0% >= 2.5%

    def test_open_above_band_low_rvol_excluded(self):
        # Caso OSUR: abrió sobre la banda
        r = evaluate_options_daily_runway("OSUR", "CALL", 4.12, 4.07, 3.0, rvol=1.9)
        assert not r["approved"]

    def test_no_data_does_not_block(self):
        r = evaluate_options_daily_runway("MARA", "CALL", 0.0, 12.0, 8.0)
        assert r["approved"] and r["mode"] == "NO_DATA"


class TestRsiExhaustion:
    def test_call_blocked_on_each_timeframe(self):
        assert not evaluate_options_rsi_exhaustion("CALL", rsi_5m=73.0)["approved"]
        assert not evaluate_options_rsi_exhaustion("CALL", rsi_15m=76.0)["approved"]
        assert not evaluate_options_rsi_exhaustion("CALL", rsi_1h=75.5)["approved"]
        assert evaluate_options_rsi_exhaustion("CALL", 72.0, 75.0, 75.0)["approved"]

    def test_put_blocked_on_each_timeframe(self):
        assert not evaluate_options_rsi_exhaustion("PUT", rsi_5m=27.0)["approved"]
        assert not evaluate_options_rsi_exhaustion("PUT", rsi_15m=29.0)["approved"]
        assert not evaluate_options_rsi_exhaustion("PUT", rsi_1h=39.0)["approved"]
        assert evaluate_options_rsi_exhaustion("PUT", 28.0, 30.0, 40.0)["approved"]

    def test_missing_values_are_skipped(self):
        assert evaluate_options_rsi_exhaustion("CALL")["approved"]


class TestTrend1H:
    def test_call_requires_ema3_above_ema9_and_rising(self):
        assert evaluate_options_1h_trend("CALL", 10.5, 10.0, 10.3)["approved"]
        assert not evaluate_options_1h_trend("CALL", 9.9, 10.0, 9.8)["approved"]
        assert not evaluate_options_1h_trend("CALL", 10.5, 10.0, 10.6)["approved"]

    def test_put_requires_ema3_below_ema9_and_falling(self):
        assert evaluate_options_1h_trend("PUT", 9.5, 10.0, 9.7)["approved"]
        assert not evaluate_options_1h_trend("PUT", 10.1, 10.0, 10.2)["approved"]
        assert not evaluate_options_1h_trend("PUT", 9.5, 10.0, 9.4)["approved"]


class TestGatekeeper:
    def test_blocks_on_runway_first(self):
        df5 = _df(_oscillating())
        r = evaluate_options_entry_gatekeeper("MARA", "CALL", df5, None, None, bb_upper_1d=100.5, bb_lower_1d=80.0)
        assert not r["approved"] and r["stage"] == "RUNWAY"

    def test_blocks_call_on_bearish_1h(self):
        df5 = _df(_oscillating())
        down = _df([120 - i for i in range(40)])
        r = evaluate_options_entry_gatekeeper("MARA", "CALL", df5, None, down, bb_upper_1d=130.0, bb_lower_1d=80.0)
        assert not r["approved"] and r["stage"] in ("RSI", "TREND_1H")

    def test_approves_call_on_bullish_1h(self):
        df5 = _df(_oscillating())
        up = _df(_trend_1h(+1))
        r = evaluate_options_entry_gatekeeper("MARA", "CALL", df5, None, up, bb_upper_1d=130.0, bb_lower_1d=80.0)
        assert r["approved"] and r["stage"] == "OK", r["reason"]

    def test_approves_put_on_bearish_1h(self):
        # 5m oscilante con última vela roja (presión vendedora); 1H bajista con retrocesos
        closes = _oscillating()
        df5 = pd.DataFrame({
            "open": [c + 0.02 for c in closes],
            "high": [c + 0.05 for c in closes],
            "low": [c - 0.05 for c in closes],
            "close": closes,
            "volume": [100_000] * len(closes),
        })
        dn = _df(_trend_1h(-1))
        r = evaluate_options_entry_gatekeeper("MARA", "PUT", df5, None, dn, bb_upper_1d=130.0, bb_lower_1d=70.0)
        assert r["approved"] and r["stage"] == "OK", r["reason"]

    def test_blocks_put_on_bullish_1h(self):
        df5 = _df(_oscillating())
        down5 = _df([100 - 0.01 * i for i in range(40)])
        up = _df([100 + i * 0.4 + (0.6 if i % 3 == 0 else -0.2) for i in range(40)])
        r = evaluate_options_entry_gatekeeper("MARA", "PUT", down5, None, up, bb_upper_1d=130.0, bb_lower_1d=70.0)
        assert not r["approved"]
        assert r["stage"] in ("RSI", "TREND_1H")


class TestTrancheIntegration:
    def test_tranche1_call_excluded_by_runway(self, monkeypatch):
        monkeypatch.setattr(opt, "_get_daily_bb_bounds", lambda t, p: (100.5, 80.0))
        df5 = _df(_oscillating())
        up = _df([100 + i * 0.3 for i in range(40)])
        r = evaluate_options_gap_entry_tranches("MARA", df5, None, up, gap_pct=6.0, direction="CALL")
        assert not r["should_enter"]
        assert "Runway" in r["reason"]

    def test_tranche1_put_excluded_by_runway(self, monkeypatch):
        monkeypatch.setattr(opt, "_get_daily_bb_bounds", lambda t, p: (130.0, 99.5))
        df5 = _df(_oscillating())
        dn = _df([120 - i * 0.3 for i in range(40)])
        r = evaluate_options_gap_entry_tranches("MARA", df5, None, dn, gap_pct=-6.0, direction="PUT")
        assert not r["should_enter"]
        assert "Runway" in r["reason"]

    def test_tranche1_call_blocked_by_1h_trend_not_bypassed_by_open(self, monkeypatch):
        monkeypatch.setattr(opt, "_get_daily_bb_bounds", lambda t, p: (140.0, 80.0))
        df5 = _df(_oscillating())
        # 1H cae y luego repunta: EMA3 sigue bajo EMA9
        c = [120 - i * 0.8 for i in range(38)] + [90.0, 90.5]
        r = evaluate_options_gap_entry_tranches("MARA", df5, None, _df(c), gap_pct=6.0, direction="CALL")
        assert not r["should_enter"]
