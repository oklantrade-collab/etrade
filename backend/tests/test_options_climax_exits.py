"""Unit tests for Options Climax Exits (Ross Cameron) & Momentum Guard in exit_engine.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timezone
import pandas as pd
import numpy as np

from app.options.exit_engine import (
    evaluate_technical_rules_and_stops,
    _compute_adx_and_di,
    _compute_rvol,
)


def test_compute_adx_and_rvol():
    """Verify ADX and RVOL computation on simulated price series."""
    # Create synthetic price dataframe
    n = 30
    dates = pd.date_range("2026-10-30 09:30", periods=n, freq="15min")
    df = pd.DataFrame({
        "open": np.linspace(100, 115, n),
        "high": np.linspace(101, 116, n),
        "low": np.linspace(99, 114, n),
        "close": np.linspace(100.5, 115.5, n),
        "volume": [1000] * 29 + [300],  # Last candle volume dropped significantly
    }, index=dates)

    cur_adx, prev_adx, cur_p_di, cur_m_di = _compute_adx_and_di(df, period=14)
    assert cur_adx > 0.0
    assert cur_p_di > cur_m_di  # Strong uptrend, +DI should exceed -DI

    rvol = _compute_rvol(df, window=20)
    assert rvol < 0.5  # 300 / 1000 = 0.30x


def test_rule_1_bollinger_climax_partial_exit_put():
    """Verify 50% partial exit on Lower Bollinger touch for long_put with profit >= 10%."""
    position = {
        "id": 436,
        "symbol": "BABA_PUT",
        "direction": "long_put",
        "qty": 2,
        "entry_underlying_price": 100.0,
        "entry_total_invested": 900.0,
        "unrealized_pnl": 150.0,
        "unrealized_pnl_pct": 16.67,
        "created_at": "2026-10-30T10:00:00+00:00",
        "exit_plan": {
            "stop_loss_underlying": 101.5,
            "partial_tp_taken": False,
            "highest_pnl_usd": 150.0,
        },
    }
    tech = {
        "valid": True,
        "symbol": "BABA",
        "current_price": 96.0,
        "bb_lower_15m": 96.5,  # Price 96.0 < 96.5 (pierced lower band)
        "bb_upper_15m": 102.0,
        "candle_closed_low_15m": 96.0,
        "is_bb_expanding_15m": True,
        "rvol_15m": 0.35,  # Exhausted volume, NOT strong momentum
        "adx_15m": 22.0,
        "adx_slope_15m": -0.5,
        "plus_di_15m": 15.0,
        "minus_di_15m": 35.0,
    }
    now_dt = datetime.fromisoformat("2026-10-30T10:30:00+00:00")

    should_exit, reason, info = evaluate_technical_rules_and_stops(
        position=position,
        tech=tech,
        now_dt=now_dt,
    )

    assert should_exit is True
    assert reason == "tp_bb_climax_partial"
    assert info["exit_ratio"] == 0.5
    assert "Take Profit Parcial (50%)" in info["detail"]


def test_momentum_guard_blocks_climax_exit_when_volume_and_adx_high():
    """Verify Momentum Guard prevents cutting winners short during strong trend."""
    position = {
        "id": 436,
        "symbol": "BABA_PUT",
        "direction": "long_put",
        "qty": 2,
        "entry_underlying_price": 100.0,
        "entry_total_invested": 900.0,
        "unrealized_pnl": 150.0,
        "unrealized_pnl_pct": 16.67,
        "created_at": "2026-10-30T10:00:00+00:00",
        "exit_plan": {
            "stop_loss_underlying": 101.5,
            "partial_tp_taken": False,
        },
    }
    tech = {
        "valid": True,
        "symbol": "BABA",
        "current_price": 96.0,
        "bb_lower_15m": 96.5,  # Pierced lower band
        "bb_upper_15m": 102.0,
        "is_bb_expanding_15m": True,
        "rvol_15m": 1.85,  # High volume!
        "adx_15m": 32.0,   # Strong trend!
        "adx_slope_15m": 1.5,  # Accelerating
        "plus_di_15m": 12.0,
        "minus_di_15m": 38.0,  # Bearish aligned
    }
    now_dt = datetime.fromisoformat("2026-10-30T10:30:00+00:00")

    should_exit, reason, info = evaluate_technical_rules_and_stops(
        position=position,
        tech=tech,
        now_dt=now_dt,
    )

    # Momentum Guard must block the exit so trend can run
    assert should_exit is False
    assert reason is None
    assert "Candado de Momentum activo" in info["detail"]


def test_rule_2_peak_profit_ratchet_giveback():
    """Verify Peak Profit Ratchet triggers when giving back >15% of peak profit."""
    position = {
        "id": 433,
        "symbol": "BAC_PUT",
        "direction": "long_put",
        "qty": 2,
        "entry_underlying_price": 50.5,
        "entry_total_invested": 600.0,
        "unrealized_pnl": 130.0,  # Dropped from $180 peak
        "unrealized_pnl_pct": 21.67,
        "created_at": "2026-10-30T10:00:00+00:00",
        "exit_plan": {
            "stop_loss_underlying": 51.0,
            "highest_pnl_usd": 180.0,  # Floor is 180 * 0.85 = $153.0. Current $130 < $153!
            "highest_pnl_pct": 30.0,
        },
    }
    tech = {
        "valid": True,
        "symbol": "BAC",
        "current_price": 49.95,
        "bb_lower_15m": 49.70,
        "bb_upper_15m": 50.80,
        "is_bb_expanding_15m": False,
        "rvol_15m": 0.45,
        "ema3_15m": 49.90,
        "prev_ema3_15m": 49.80,  # Bounced up on PUT (price 49.95 > 49.80 => retreating)
    }
    now_dt = datetime.fromisoformat("2026-10-30T10:45:00+00:00")

    should_exit, reason, info = evaluate_technical_rules_and_stops(
        position=position,
        tech=tech,
        now_dt=now_dt,
    )

    assert should_exit is True
    assert reason == "tp_peak_profit_ratchet"
    assert info["exit_ratio"] == 1.0
    assert "PnL retrocedió >15% del pico" in info["detail"]


def test_rule_3_rvol_exhaustion():
    """Verify Volume Exhaustion triggers when RVOL <= 0.40x near outer Bollinger band."""
    position = {
        "id": 440,
        "symbol": "AAPL_CALL",
        "direction": "long_call",
        "qty": 1,
        "entry_underlying_price": 230.0,
        "entry_total_invested": 500.0,
        "unrealized_pnl": 55.0,
        "unrealized_pnl_pct": 11.0,  # >= 8.0%
        "created_at": "2026-10-30T10:00:00+00:00",
        "exit_plan": {
            "stop_loss_underlying": 228.0,
        },
    }
    tech = {
        "valid": True,
        "symbol": "AAPL",
        "current_price": 234.90,
        "bb_upper_15m": 235.0,  # Within 0.998 of upper band
        "bb_lower_15m": 228.0,
        "is_bb_expanding_15m": False,
        "rvol_15m": 0.25,  # <= 0.40x volume dried up
        "adx_15m": 20.0,
    }
    now_dt = datetime.fromisoformat("2026-10-30T10:40:00+00:00")

    should_exit, reason, info = evaluate_technical_rules_and_stops(
        position=position,
        tech=tech,
        now_dt=now_dt,
    )

    assert should_exit is True
    assert reason == "tp_rvol_exhaustion"
    assert info["exit_ratio"] == 1.0
    assert "Agotamiento de Volumen" in info["detail"]
