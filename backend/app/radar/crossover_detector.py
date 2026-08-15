"""
Crossover and Discrete Event Detector for RADAR.
eTrade v5.0 — Spec Section 2.2 & 3.2
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from app.radar.config import CROSSOVER_PAIRS


def detect_ema_crossovers(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Detects if any EMA crossover occurred between the last two closed candles.
    Uses iloc[-3] (previous closed) vs iloc[-2] (current closed).
    
    Returns list of detected event dictionaries:
        [{
            'event_type': 'cruce_EMA3_EMA9',
            'direction': 'bullish' | 'bearish',
            'fast_col': 'ema_3',
            'slow_col': 'ema_9',
            'price': float,
            'timestamp': str,
            'detail': str
        }]
    """
    events = []
    if df is None or len(df) < 3:
        return events

    prev_candle = df.iloc[-3]
    curr_candle = df.iloc[-2]

    curr_price = float(curr_candle.get('close', 0.0))
    ts_now = datetime.now(timezone.utc).isoformat()

    for fast_col, slow_col, event_name in CROSSOVER_PAIRS:
        if fast_col not in df.columns or slow_col not in df.columns:
            continue

        prev_fast = prev_candle.get(fast_col)
        prev_slow = prev_candle.get(slow_col)
        curr_fast = curr_candle.get(fast_col)
        curr_slow = curr_candle.get(slow_col)

        if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
            continue

        # Bullish cross: fast crossed above slow
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            events.append({
                'event_type': event_name,
                'direction': 'bullish',
                'fast_col': fast_col,
                'slow_col': slow_col,
                'price': curr_price,
                'timestamp': ts_now,
                'detail': f"{fast_col} ({curr_fast:.5f}) crossed ABOVE {slow_col} ({curr_slow:.5f})"
            })
        # Bearish cross: fast crossed below slow
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            events.append({
                'event_type': event_name,
                'direction': 'bearish',
                'fast_col': fast_col,
                'slow_col': slow_col,
                'price': curr_price,
                'timestamp': ts_now,
                'detail': f"{fast_col} ({curr_fast:.5f}) crossed BELOW {slow_col} ({curr_slow:.5f})"
            })

    return events


def detect_fibonacci_crossover(prev_zone: Optional[int], curr_zone: int, price: float) -> Optional[Dict[str, Any]]:
    """
    Detects transition from one Fibonacci zone to another.
    """
    if prev_zone is None or prev_zone == curr_zone:
        return None

    # Determine event naming (e.g. cruce_fibonacci_LOWER_2)
    zone_label = f"LOWER_{abs(curr_zone)}" if curr_zone < 0 else f"UPPER_{curr_zone}" if curr_zone > 0 else "BASIS"
    event_type = f"cruce_fibonacci_{zone_label}"
    direction = 'bullish' if curr_zone > prev_zone else 'bearish'

    return {
        'event_type': event_type,
        'direction': direction,
        'from_zone': prev_zone,
        'to_zone': curr_zone,
        'price': price,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'detail': f"Fibonacci zone transition from {prev_zone} to {curr_zone}"
    }


def detect_impulse_candle(df_15m: pd.DataFrame, threshold_ratio: float = 1.8) -> Optional[Dict[str, Any]]:
    """
    Detects if the last closed 15m candle is an impulse candle (range > 1.8 * ATR).
    """
    if df_15m is None or len(df_15m) < 2:
        return None

    candle = df_15m.iloc[-2]
    high = float(candle.get('high', 0.0))
    low = float(candle.get('low', 0.0))
    open_p = float(candle.get('open', 0.0))
    close_p = float(candle.get('close', 0.0))
    atr = float(candle.get('atr', 0.0))

    if atr <= 0:
        return None

    candle_range = high - low
    if candle_range > threshold_ratio * atr:
        direction = 'bullish' if close_p > open_p else 'bearish'
        return {
            'event_type': 'vela_impulso',
            'direction': direction,
            'range': round(candle_range, 6),
            'atr': round(atr, 6),
            'ratio': round(candle_range / atr, 2),
            'price': close_p,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'detail': f"Impulse candle detected: range={candle_range:.5f} ({candle_range/atr:.1f}x ATR)"
        }
    return None
