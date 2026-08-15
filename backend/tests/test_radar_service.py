"""
Unit tests for RADAR module.
"""
import pytest
import pandas as pd
import numpy as np

from app.radar.slope_classifier import classify_slope, get_slope_matrix_interpretation
from app.radar.crossover_detector import detect_ema_crossovers, detect_fibonacci_crossover, detect_impulse_candle
from app.radar.event_bus import RadarEventBus


def test_classify_slope_ascending():
    # 10 candles with increasing EMA values
    df = pd.DataFrame({
        'ema_3': [100.0 + i * 2.0 for i in range(10)],
        'atr': [1.0] * 10
    })
    res = classify_slope(df, 'ema_3', lookback=3)
    assert res['classification'] == 'ascending'
    assert res['slope_normalized'] > 0.15


def test_classify_slope_descending():
    df = pd.DataFrame({
        'ema_3': [100.0 - i * 2.0 for i in range(10)],
        'atr': [1.0] * 10
    })
    res = classify_slope(df, 'ema_3', lookback=3)
    assert res['classification'] == 'descending'
    assert res['slope_normalized'] < -0.15


def test_classify_slope_lateral():
    df = pd.DataFrame({
        'ema_3': [100.0, 100.05, 100.02, 100.04, 100.03, 100.05, 100.04, 100.06, 100.05, 100.05],
        'atr': [1.0] * 10
    })
    res = classify_slope(df, 'ema_3', lookback=3)
    assert res['classification'] == 'lateral'


def test_slope_matrix_interpretation():
    # Strong trend bullish
    m1 = get_slope_matrix_interpretation('ascending', 'ascending')
    assert m1['is_strong_trend'] is True

    # Pullback in intact bullish trend
    m2 = get_slope_matrix_interpretation('descending', 'ascending')
    assert m2['is_pullback_noise'] is True

    # Real reversal probable
    m3 = get_slope_matrix_interpretation('descending', 'descending')
    assert m3['is_real_reversal'] is True


def test_detect_ema_crossovers():
    df = pd.DataFrame({
        'ema_3': [90.0, 95.0, 105.0, 110.0],
        'ema_9': [100.0, 100.0, 100.0, 100.0],
        'close': [95.0, 98.0, 106.0, 109.0]
    })
    # iloc[-3] has ema_3=95 vs ema_9=100. iloc[-2] has ema_3=105 vs ema_9=100 -> Bullish cross
    events = detect_ema_crossovers(df)
    assert len(events) >= 1
    assert events[0]['event_type'] == 'cruce_EMA3_EMA9'
    assert events[0]['direction'] == 'bullish'


def test_detect_fibonacci_crossover():
    ev = detect_fibonacci_crossover(prev_zone=-1, curr_zone=-2, price=1.0850)
    assert ev is not None
    assert ev['event_type'] == 'cruce_fibonacci_LOWER_2'
    assert ev['direction'] == 'bearish'


def test_detect_impulse_candle():
    df = pd.DataFrame({
        'open': [100.0, 100.0, 100.0],
        'high': [101.0, 105.0, 102.0],
        'low': [99.0, 98.0, 99.0],
        'close': [100.0, 104.5, 101.0],
        'atr': [1.0, 1.0, 1.0]
    })
    # iloc[-2] range is 105 - 98 = 7.0 > 1.8 * 1.0 -> Bullish impulse
    ev = detect_impulse_candle(df, threshold_ratio=1.8)
    assert ev is not None
    assert ev['event_type'] == 'vela_impulso'
    assert ev['direction'] == 'bullish'
