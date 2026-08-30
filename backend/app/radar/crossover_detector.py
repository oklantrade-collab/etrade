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


def detect_bollinger_squeeze_pierce(df_15m: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Detects if 15m candle pierced Bollinger Upper/Lower band during or after Squeeze.
    """
    events = []
    if df_15m is None or len(df_15m) < 20:
        return events

    df = df_15m.copy()
    if 'sma20' not in df.columns:
        df['sma20'] = df['close'].rolling(20).mean()
    if 'std20' not in df.columns:
        df['std20'] = df['close'].rolling(20).std()

    sma20 = float(df['sma20'].iloc[-1])
    std20 = float(df['std20'].iloc[-1])
    if std20 <= 0 or pd.isna(sma20):
        return events

    upper_bb = sma20 + 2.0 * std20
    lower_bb = sma20 - 2.0 * std20
    bandwidth = (upper_bb - lower_bb) / sma20 if sma20 > 0 else 0.0

    candle = df.iloc[-1]
    high = float(candle.get('high', 0.0))
    low = float(candle.get('low', 0.0))
    close_p = float(candle.get('close', 0.0))
    ts_now = datetime.now(timezone.utc).isoformat()

    # Lower Pierce (Bullish Rebound potential)
    if low <= lower_bb:
        events.append({
            'event_type': 'cruce_bollinger_LOWER',
            'direction': 'bullish',
            'bandwidth': round(bandwidth, 6),
            'lower_bb': round(lower_bb, 5),
            'sma20': round(sma20, 5),
            'price': close_p,
            'timestamp': ts_now,
            'detail': f"Low ({low:.5f}) pierced Lower Bollinger Band ({lower_bb:.5f}) | Bandwidth={bandwidth:.4f}"
        })

    # Upper Pierce (Bearish Rebound potential)
    if high >= upper_bb:
        events.append({
            'event_type': 'cruce_bollinger_UPPER',
            'direction': 'bearish',
            'bandwidth': round(bandwidth, 6),
            'upper_bb': round(upper_bb, 5),
            'sma20': round(sma20, 5),
            'price': close_p,
            'timestamp': ts_now,
            'detail': f"High ({high:.5f}) pierced Upper Bollinger Band ({upper_bb:.5f}) | Bandwidth={bandwidth:.4f}"
        })

    return events


def detect_extremo_opportunity(
    df_15m: pd.DataFrame,
    df_1d: Optional[pd.DataFrame] = None,
    symbol: str = 'GBPUSD',
    is_forex: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Detects autonomous high-conviction sniper opportunity (BB_EXTREMO_SNIPER):
    1. Macro 1D Direction Check (EMA3 vs EMA9).
    2. 15m Bollinger Band Pierce/Roce (Low <= LowerBB or High >= UpperBB).
    3. 15m Bollinger Band Curvature Check:
       - LONG: Lower BB must be FLAT or ASCENDING (LowerBB[-1] >= LowerBB[-2] - tol).
       - SHORT: Upper BB must be FLAT or DESCENDING (UpperBB[-1] <= UpperBB[-2] + tol).
    4. Extreme Condition: is_squeeze == True OR (RSI_15m <= 35 for Long, RSI_15m >= 65 for Short).
    Returns order proposal dict or None.
    """
    if df_15m is None or len(df_15m) < 22:
        return None

    df = df_15m.copy()
    if 'sma20' not in df.columns:
        df['sma20'] = df['close'].rolling(20).mean()
    if 'std20' not in df.columns:
        df['std20'] = df['close'].rolling(20).std()

    if len(df.dropna(subset=['sma20', 'std20'])) < 2:
        return None

    if 'upper_bb' not in df.columns:
        df['upper_bb'] = df['sma20'] + 2.0 * df['std20']
    if 'lower_bb' not in df.columns:
        df['lower_bb'] = df['sma20'] - 2.0 * df['std20']
    
    # Calculate RSI 14
    if 'rsi' not in df.columns:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))

    curr_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    curr_lower_bb = float(curr_row['lower_bb'])
    prev_lower_bb = float(prev_row['lower_bb'])
    curr_upper_bb = float(curr_row['upper_bb'])
    prev_upper_bb = float(prev_row['upper_bb'])
    sma20 = float(curr_row['sma20'])
    rsi_15m = float(curr_row['rsi']) if not pd.isna(curr_row['rsi']) else 50.0

    bandwidth = (curr_upper_bb - curr_lower_bb) / sma20 if sma20 > 0 else 0.0
    sq_thresh = 0.0030 if is_forex else 0.015
    is_squeeze = bool(bandwidth <= sq_thresh)

    high = float(curr_row['high'])
    low = float(curr_row['low'])
    close_p = float(curr_row['close'])
    atr = float(curr_row.get('atr', (curr_upper_bb - curr_lower_bb) * 0.15))

    # Macro 1D Bias Check
    macro_bullish = True
    macro_bearish = True
    if df_1d is not None and len(df_1d) >= 10:
        df_1d_c = df_1d.copy()
        if 'ema_3' not in df_1d_c.columns:
            df_1d_c['ema_3'] = df_1d_c['close'].ewm(span=3, adjust=False).mean()
        if 'ema_9' not in df_1d_c.columns:
            df_1d_c['ema_9'] = df_1d_c['close'].ewm(span=9, adjust=False).mean()
        ema3_1d = float(df_1d_c['ema_3'].iloc[-1])
        ema9_1d = float(df_1d_c['ema_9'].iloc[-1])
        macro_bullish = (ema3_1d > ema9_1d)
        macro_bearish = (ema3_1d < ema9_1d)

    tol = 0.00015 if is_forex else 0.5
    band_slope_tol = 0.00005 if is_forex else 0.1

    # --- LONG Evaluation ---
    if macro_bullish and (low <= curr_lower_bb + tol):
        # Curvature Check: Lower BB must be FLAT or ASCENDING
        lower_bb_flat_or_ascending = (curr_lower_bb >= prev_lower_bb - band_slope_tol)
        if lower_bb_flat_or_ascending:
            # Extreme or Squeeze check
            if is_squeeze or rsi_15m <= 35.0:
                limit_p = round(curr_lower_bb, 5 if is_forex else 2)
                sl_p = round(min(low, limit_p) - 1.5 * atr, 5 if is_forex else 2)
                tp1_p = round(sma20, 5 if is_forex else 2)
                tp2_p = round(curr_upper_bb, 5 if is_forex else 2)
                return {
                    'strategy': 'BB_EXTREMO_SNIPER',
                    'symbol': symbol,
                    'side': 'buy',
                    'order_type': 'LIMIT',
                    'limit_price': limit_p,
                    'stop_loss': sl_p,
                    'take_profit_1': tp1_p,
                    'take_profit_2': tp2_p,
                    'rsi_15m': round(rsi_15m, 1),
                    'bandwidth': round(bandwidth, 6),
                    'is_squeeze': is_squeeze,
                    'detail': f"BB Sniper LONG: Lower BB Curled Flat/Asc (prev={prev_lower_bb:.5f}, curr={curr_lower_bb:.5f}), RSI={rsi_15m:.1f}, Squeeze={is_squeeze}"
                }

    # --- SHORT Evaluation ---
    if macro_bearish and (high >= curr_upper_bb - tol):
        # Curvature Check: Upper BB must be FLAT or DESCENDING
        upper_bb_flat_or_descending = (curr_upper_bb <= prev_upper_bb + band_slope_tol)
        if upper_bb_flat_or_descending:
            # Extreme or Squeeze check
            if is_squeeze or rsi_15m >= 65.0:
                limit_p = round(curr_upper_bb, 5 if is_forex else 2)
                sl_p = round(max(high, limit_p) + 1.5 * atr, 5 if is_forex else 2)
                tp1_p = round(sma20, 5 if is_forex else 2)
                tp2_p = round(curr_lower_bb, 5 if is_forex else 2)
                return {
                    'strategy': 'BB_EXTREMO_SNIPER',
                    'symbol': symbol,
                    'side': 'sell',
                    'order_type': 'LIMIT',
                    'limit_price': limit_p,
                    'stop_loss': sl_p,
                    'take_profit_1': tp1_p,
                    'take_profit_2': tp2_p,
                    'rsi_15m': round(rsi_15m, 1),
                    'bandwidth': round(bandwidth, 6),
                    'is_squeeze': is_squeeze,
                    'detail': f"BB Sniper SHORT: Upper BB Curled Flat/Desc (prev={prev_upper_bb:.5f}, curr={curr_upper_bb:.5f}), RSI={rsi_15m:.1f}, Squeeze={is_squeeze}"
                }

    return None


