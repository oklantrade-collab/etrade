import pytest
import pandas as pd
import numpy as np
from app.core.breakpoint_detector import BreakpointDetector, BreakpointEvent

def make_df_15m(rows):
    """Helper to create a 15m DataFrame from list of dicts.
    Always includes an extra forming candle at the end."""
    data = list(rows)
    # Add a dummy forming candle at the end
    data.append(dict(data[-1]))
    return pd.DataFrame(data)

def test_breakpoint_bullish_cross_short_aligned():
    detector = BreakpointDetector()
    
    # 3 closed candles
    # Candle 0: short aligned, price low
    # Candle 1: short aligned (ema3 < ema9 < ema20), price below ema9 & ema20
    # Candle 2: price crosses above ema9
    rows = [
        {'close': 90.0, 'high': 92.0, 'low': 88.0, 'ema_3': 92.0, 'ema_9': 95.0, 'ema_20': 100.0},
        {'close': 91.0, 'high': 93.0, 'low': 89.0, 'ema_3': 91.5, 'ema_9': 94.5, 'ema_20': 99.5},
        {'close': 96.0, 'high': 97.0, 'low': 90.5, 'ema_3': 93.0, 'ema_9': 94.0, 'ema_20': 99.0},
    ]
    df = make_df_15m(rows)
    event = detector.detect(df)
    
    assert event.detected is True
    assert event.direction == 'bullish_cross'
    assert event.prior_regime == 'short_aligned'
    assert event.crossed_ema == 'ema9'
    assert event.structure == 'HH_HL'

def test_breakpoint_bearish_cross_long_aligned():
    detector = BreakpointDetector()
    
    # Candle 0: long aligned
    # Candle 1: long aligned (ema3 > ema9 > ema20), price above ema9 & ema20
    # Candle 2: price crosses below ema9 and ema20
    rows = [
        {'close': 110.0, 'high': 112.0, 'low': 108.0, 'ema_3': 108.0, 'ema_9': 105.0, 'ema_20': 100.0},
        {'close': 109.0, 'high': 111.0, 'low': 107.0, 'ema_3': 108.5, 'ema_9': 105.5, 'ema_20': 100.5},
        {'close': 99.0, 'high': 106.0, 'low': 98.0, 'ema_3': 105.0, 'ema_9': 104.0, 'ema_20': 101.0},
    ]
    df = make_df_15m(rows)
    event = detector.detect(df)
    
    assert event.detected is True
    assert event.direction == 'bearish_cross'
    assert event.prior_regime == 'long_aligned'
    assert event.crossed_ema == 'both'
    assert event.structure == 'LH_LL'

def test_no_alignment():
    detector = BreakpointDetector()
    rows = [
        {'close': 100.0, 'high': 102.0, 'low': 98.0, 'ema_3': 100.0, 'ema_9': 105.0, 'ema_20': 95.0},
        {'close': 101.0, 'high': 103.0, 'low': 99.0, 'ema_3': 100.5, 'ema_9': 104.5, 'ema_20': 95.5},
        {'close': 106.0, 'high': 107.0, 'low': 100.0, 'ema_3': 102.0, 'ema_9': 104.0, 'ema_20': 96.0},
    ]
    df = make_df_15m(rows)
    event = detector.detect(df)
    
    assert event.detected is False
    assert "No clear EMA alignment" in event.detail

def test_insufficient_data():
    detector = BreakpointDetector()
    df = pd.DataFrame([{'close': 100.0, 'high': 102.0, 'low': 98.0, 'ema_3': 100.0, 'ema_9': 95.0, 'ema_20': 90.0}])
    event = detector.detect(df)
    assert event.detected is False
    assert "Not enough" in event.detail
