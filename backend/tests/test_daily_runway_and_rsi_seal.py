import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import pandas as pd
import numpy as np
from app.stocks.aduana_gap_runner_engine import (
    evaluate_daily_runway_feasibility,
    evaluate_gap_runner_entry_tranches
)
from app.stocks.fast_track_runner_engine import (
    evaluate_fast_track_entry,
    evaluate_leg2_reversal_entry
)


def _make_df(candles):
    df = pd.DataFrame(candles)
    # Give it a range index
    return df


class TestDailyRunwayAndRSISeal:

    def test_doug_rejected_by_daily_runway(self):
        """Caso real DOUG: Open=1.60, BB_Upper_1D=1.61, RVOL=0.11x -> Espacio paupérrimo (+0.6%) DEBE ser RECHAZADO."""
        res = evaluate_daily_runway_feasibility(
            open_price=1.60,
            bb_upper_1d=1.61,
            rvol=0.11,
            min_required_runway_pct=25.0
        )
        assert res["approved"] is False
        assert res["runway_pct"] < 25.0
        assert "insuficiente" in res["reason"]

    def test_osur_rejected_by_daily_runway(self):
        """Caso real OSUR: Open=4.12, BB_Upper_1D=4.07, RVOL=1.90x -> Abrió sobre la banda (-0.2%) DEBE ser RECHAZADO."""
        res = evaluate_daily_runway_feasibility(
            open_price=4.12,
            bb_upper_1d=4.07,
            rvol=1.90,
            min_required_runway_pct=25.0
        )
        assert res["approved"] is False
        assert res["runway_pct"] < 0.0

    def test_high_rvol_super_runner_with_room_approved(self):
        """Caso Super-Runner: Open=10.00, BB_Upper_1D=11.50, RVOL=5.0x -> Delta RVOL expande el techo y APRUEBA."""
        res = evaluate_daily_runway_feasibility(
            open_price=10.00,
            bb_upper_1d=11.50,
            rvol=5.0,
            min_required_runway_pct=25.0
        )
        assert res["approved"] is True
        assert res["delta_rvol_pct"] > 0
        assert res["runway_pct"] >= 25.0

    def test_rvol_ge_2_relaxes_runway_to_11pct(self):
        """Valida regla de 11 pct: Con RVOL >= 2.0x, acciones como ENVX (+15 pct), CRML (+19 pct) o AEYE (+12.1 pct) son APROBADAS."""
        # Caso AEYE / ENVX: runway ~ 15%
        res_approved = evaluate_daily_runway_feasibility(
            open_price=10.00,
            bb_upper_1d=11.10,
            rvol=2.2,
            min_required_runway_pct=25.0
        )
        assert res_approved["approved"] is True
        assert 11.0 <= res_approved["runway_pct"] < 25.0
        assert "Requerido: 11%" in res_approved["reason"]

        # Si RVOL < 2.0x (ej. 1.5x), el 15% de runway NO alcanza (requiere 25%) y debe ser RECHAZADO
        res_rejected_low_rvol = evaluate_daily_runway_feasibility(
            open_price=10.00,
            bb_upper_1d=11.10,
            rvol=1.5,
            min_required_runway_pct=25.0
        )
        assert res_rejected_low_rvol["approved"] is False
        assert "< 25%" in res_rejected_low_rvol["reason"]

        # Si RVOL >= 2.0x pero runway < 11% (ej. 8%), debe ser RECHAZADO
        res_rejected_tight = evaluate_daily_runway_feasibility(
            open_price=10.00,
            bb_upper_1d=10.40,
            rvol=2.5,
            min_required_runway_pct=25.0
        )
        assert res_rejected_tight["approved"] is False
        assert "< 11%" in res_rejected_tight["reason"]

    def test_rsi_exhaustion_blocks_fast_track_entry(self):
        """Valida que evaluate_fast_track_entry rechace si RSI 5m > 75.0 (como SGRY con RSI 97)."""
        # Crear 20 velas de 5m en subida vertical continua para que RSI supere 85
        c_series = [10.0 + i * 0.8 for i in range(25)]
        df_5m = pd.DataFrame({
            'open': [c - 0.2 for c in c_series],
            'high': [c + 0.3 for c in c_series],
            'low': [c - 0.4 for c in c_series],
            'close': c_series,
            'volume': [500_000 for _ in range(25)]
        })
        df_15m = pd.DataFrame({
            'open': [10.0, 15.0, 20.0],
            'high': [15.0, 20.0, 28.0],
            'low': [9.8, 14.8, 19.8],
            'close': [14.9, 19.9, 27.5],
            'volume': [2_000_000 for _ in range(3)]
        })
        res = evaluate_fast_track_entry(
            ticker="PUMP",
            df_5m=df_5m,
            df_15m=df_15m,
            df_1h=None,
            df_1d=None,
            gap_pct=40.0,
            config={'skip_daily_runway_check': True}
        )
        assert res['is_valid'] is False
        assert "Anti-Agotamiento" in res['reason'] or "RSI" in res['reason']

    def test_rsi_exhaustion_blocks_aduana_gap_tranches(self):
        """Valida que evaluate_gap_runner_entry_tranches rechace si RSI 5m > 75.0."""
        c_series = [10.0 + i * 0.9 for i in range(25)]
        df_5m = pd.DataFrame({
            'open': [c - 0.1 for c in c_series],
            'high': [c + 0.3 for c in c_series],
            'low': [c - 0.3 for c in c_series],
            'close': c_series,
            'volume': [50_000 for _ in range(25)]
        })
        res = evaluate_gap_runner_entry_tranches(
            ticker="EXHAUSTED",
            df_5m=df_5m,
            df_15m=None,
            df_1h=None,
            gap_pct=25.0,
            config={'skip_time_window_check': True, 'skip_vwap_check': True, 'skip_daily_runway_check': True}
        )
        assert res['should_enter'] is False
        assert "Anti-Agotamiento" in res['reason'] or "RSI" in res['reason']


    def test_aduana_blocks_when_ema3_le_ema9_in_1h(self):
        """Valida que Aduana rechace si en 1H la EMA3 <= EMA9."""
        # 5m velas normales (RSI moderado ~57)
        c5 = [10.0, 10.2, 10.1, 10.3, 10.2, 10.1, 10.25, 10.15, 10.2, 10.1, 10.2, 10.15, 10.25, 10.18, 10.22]
        df_5m = pd.DataFrame({
            'open': [c - 0.05 for c in c5],
            'high': [c + 0.10 for c in c5],
            'low': [c - 0.10 for c in c5],
            'close': c5,
            'volume': [50_000 for _ in range(len(c5))]
        })
        # 1H en caída donde EMA3 < EMA9 (ej. de 15.0 bajando a 10.4)
        c1h = [15.0, 14.5, 14.0, 13.5, 13.0, 12.5, 12.0, 11.5, 11.0, 10.5, 10.22]
        df_1h = pd.DataFrame({
            'open': [c + 0.2 for c in c1h],
            'high': [c + 0.4 for c in c1h],
            'low': [c - 0.2 for c in c1h],
            'close': c1h,
            'volume': [500_000 for _ in range(len(c1h))]
        })
        res = evaluate_gap_runner_entry_tranches(
            ticker="BEAR1H",
            df_5m=df_5m,
            df_15m=None,
            df_1h=df_1h,
            gap_pct=15.0,
            config={'skip_time_window_check': True, 'skip_vwap_check': True, 'skip_daily_runway_check': True}
        )
        assert res['should_enter'] is False
        assert "EMA3" in res['reason'] and "EMA9" in res['reason']

    def test_fast_track_blocks_when_ema3_le_ema9_in_1h(self):
        """Valida que Fast Track rechace si en 1H la EMA3 <= EMA9."""
        c5 = [10.0, 10.2, 10.1, 10.3, 10.2, 10.1, 10.25, 10.15, 10.2, 10.1, 10.2, 10.15, 10.25, 10.18, 10.22]
        df_5m = pd.DataFrame({
            'open': [c - 0.05 for c in c5],
            'high': [c + 0.10 for c in c5],
            'low': [c - 0.10 for c in c5],
            'close': c5,
            'volume': [300_000 for _ in range(len(c5))]
        })
        # 1H en caída
        c1h = [15.0, 14.5, 14.0, 13.5, 13.0, 12.5, 12.0, 11.5, 11.0, 10.5, 10.22]
        df_1h = pd.DataFrame({
            'open': [c + 0.2 for c in c1h],
            'high': [c + 0.4 for c in c1h],
            'low': [c - 0.2 for c in c1h],
            'close': c1h,
            'volume': [500_000 for _ in range(len(c1h))]
        })
        res = evaluate_fast_track_entry(
            ticker="BEAR_FT",
            df_5m=df_5m,
            df_15m=None,
            df_1h=df_1h,
            df_1d=None,
            gap_pct=15.0,
            config={'skip_daily_runway_check': True}
        )
        assert res['is_valid'] is False
        assert "EMA3" in res['reason'] and "EMA9" in res['reason']
