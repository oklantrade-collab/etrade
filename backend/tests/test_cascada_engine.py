"""
Unit tests for CASCADA engine.
"""
import pytest
import pandas as pd
import numpy as np

from app.cascada.giveback_monitor import evaluate_giveback, update_pnl_pico
from app.cascada.level_evaluator import check_rebote, check_continuacion
from app.cascada.cascada_engine import CascadaEngine


def test_update_pnl_pico():
    assert update_pnl_pico(10.0, 5.0) == 10.0
    assert update_pnl_pico(3.0, 5.0) == 5.0
    assert update_pnl_pico(4.0, None) == 4.0


def test_evaluate_giveback():
    # Peak is $10.0. Current dropped to $4.0 (< 50% of 10.0 -> < 5.0) -> Triggered!
    gb = evaluate_giveback(pnl_current=4.0, pnl_pico=10.0, threshold_pct=0.50)
    assert gb['triggered'] is True
    assert gb['floor_pnl'] == 5.0

    # Peak is $10.0. Current is $6.0 (> 5.0) -> Not triggered
    gb_ok = evaluate_giveback(pnl_current=6.0, pnl_pico=10.0, threshold_pct=0.50)
    assert gb_ok['triggered'] is False


def test_check_rebote_noise_vs_real():
    # Short position. EMA3 turns ascending, but EMA20 stays descending -> Noise / Pullback in trend
    snap_noise = {
        'pendiente_EMA3': 'ascending',
        'pendiente_EMA20': 'descending',
        'slope_matrix': {'is_pullback_noise': True}
    }
    res_noise = check_rebote('short', snap_noise, pnl_current=5.0, current_level=1)
    assert res_noise['is_rebote'] is False
    assert res_noise['reason'] == 'PULLBACK_IN_INTACT_TREND'

    # Short position. EMA3 turns ascending AND EMA20 is lateral -> Real Reversal Confirmed!
    snap_real = {
        'pendiente_EMA3': 'ascending',
        'pendiente_EMA20': 'lateral',
        'slope_matrix': {'is_real_reversal': True}
    }
    res_real = check_rebote('short', snap_real, pnl_current=5.0, current_level=1)
    assert res_real['is_rebote'] is True
    assert res_real['reason'] == 'REAL_REVERSAL_CONFIRMED'


def test_cascada_engine_giveback_close():
    engine = CascadaEngine()
    pos = {
        'id': 'pos-test-1',
        'symbol': 'EURUSD',
        'side': 'short',
        'unrealized_pnl': 3.0,
        'pnl_pico': 10.0,
        'cascade_level': 1
    }
    snap = {'status': 'ok', 'pendiente_EMA3': 'descending', 'pendiente_EMA20': 'descending'}
    events = [{'event_type': 'cruce_EMA3_EMA9', 'direction': 'bearish'}]

    res = engine.evaluate(pos, snap, events)
    assert res.decision == 'GIVEBACK_CLOSE'
    assert res.check_type == 'giveback'
    assert res.cascade_hold is False


def test_cascada_engine_continuation_and_hold():
    engine = CascadaEngine()
    pos = {
        'id': 'pos-test-2',
        'symbol': 'EURUSD',
        'side': 'short',
        'unrealized_pnl': 8.0,
        'pnl_pico': 8.0,
        'cascade_level': 0
    }
    snap = {'status': 'ok', 'pendiente_EMA3': 'descending', 'pendiente_EMA20': 'descending'}
    events = [{'event_type': 'cruce_EMA3_EMA9', 'direction': 'bearish'}]
    
    # Mock 15m DF with descending highs
    df_15m = pd.DataFrame({
        'high': [1.100, 1.095, 1.090, 1.085],
        'low': [1.090, 1.085, 1.080, 1.075],
        'close': [1.092, 1.088, 1.082, 1.078],
        'upper_6': [1.110, 1.108, 1.106, 1.104]
    })

    res = engine.evaluate(pos, snap, events, df_15m=df_15m)
    assert res.current_level == 1
    assert res.level_advanced is True
    assert res.decision == 'MANTENER'
    assert res.cascade_hold is True
