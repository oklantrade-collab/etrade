"""
eTrade v3 — Fibonacci Bollinger Bands
Core indicator: VWMA-based Fibonacci Bollinger Bands + zone classification.
Reference: PineScript f_fibonacci_bollinger() with bug fix in zone detection.
"""
import pandas as pd
import numpy as np

FIBONACCI_RATIOS = [0.236, 0.382, 0.500, 0.618, 0.764, 1.000]


def fibonacci_bollinger(
    df: pd.DataFrame,
    length: int = 200,
    mult: float = 3.0,
    src_col: str = "hlc3",
) -> pd.DataFrame:
    """
    Calculate Fibonacci Bollinger Bands.

    CRITICAL:
    1. Uses VWMA as basis (NOT SMA) — matches ta.vwma in PineScript
    2. Uses ddof=0 for population standard deviation (matches PineScript)
    3. src_col = 'hlc3' = (high + low + close) / 3

    Parameters
    ----------
    df : DataFrame with OHLCV columns (open, high, low, close, volume)
    length : lookback window for VWMA and stdev (default 200)
    mult : standard deviation multiplier (default 3.0)
    src_col : source column name

    Returns
    -------
    DataFrame with added columns:
      basis, upper_1..upper_6, lower_1..lower_6
    """
    df = df.copy()

    if src_col == "hlc3":
        df["hlc3"] = (df["high"] + df["low"] + df["close"]) / 3

    src = df[src_col]

    # Basis (VWMA)
    typical_vol = src * df["volume"]
    vol_sum = df["volume"].rolling(window=length).sum()
    basis = typical_vol.rolling(window=length).sum() / vol_sum
    df["basis"] = basis

    # Standard Deviation (Population)
    dev = mult * src.rolling(window=length).std(ddof=0)

    # Fibonacci Bands 1..6
    # Ratios: 1:0.236, 2:0.382, 3:0.500, 4:0.618, 5:0.764, 6:1.000
    ratios = [0.236, 0.382, 0.500, 0.618, 0.764, 1.000]
    for i, ratio in enumerate(ratios, start=1):
        df[f"upper_{i}"] = basis + (ratio * dev)
        df[f"lower_{i}"] = basis - (ratio * dev)

    return df


def get_fibonacci_zone(price: float, levels: dict) -> int:
    """
    Determine which Fibonacci zone the price is in.

    Equivalent to f_fibonacci_bollinger_nOp() from PineScript.
    BUG FIX: PineScript original has a bug where (nOp <= basis_fb or nOp > basis_fb)
    always returns 0. In Python, we evaluate extremes first.

    Returns: -6 ... 0 ... +6
    """
    if price <= levels["lower_6"]:
        return -6
    if price < levels["lower_5"]:
        return -5
    if price < levels["lower_4"]:
        return -4
    if price < levels["lower_3"]:
        return -3
    if price < levels["lower_2"]:
        return -2
    if price < levels["lower_1"]:
        return -1
    if price > levels["upper_6"]:
        return 6
    if price > levels["upper_5"]:
        return 5
    if price > levels["upper_4"]:
        return 4
    if price > levels["upper_3"]:
        return 3
    if price > levels["upper_2"]:
        return 2
    if price > levels["upper_1"]:
        return 1
    return 0


def extract_fib_levels(df: pd.DataFrame) -> dict:
    """
    Extract the latest Fibonacci BB levels from a processed DataFrame.
    Returns a dict with keys: basis, upper_1..6, lower_1..6, zone
    """
    last = df.iloc[-1]
    levels = {}

    for col in ["basis"]:
        levels[col] = float(last[col]) if pd.notna(last[col]) else 0.0

    for i in range(1, 7):
        for prefix in ["upper_", "lower_"]:
            key = f"{prefix}{i}"
            levels[key] = float(last[key]) if pd.notna(last[key]) else 0.0

    levels["zone"] = get_fibonacci_zone(float(last["close"]), levels)
    return levels


def get_next_fibonacci_target(
    side: str,
    current_price: float,
    current_zone: int,
    levels: dict
) -> dict:
    """
    Determina la siguiente banda Fibonacci hacia la que se dirige el precio.
    
    Para LONG: busca la siguiente banda superior (basis, upper_1...upper_6).
    Para SHORT: busca la siguiente banda inferior (basis, lower_1...lower_6).
    """
    side = (side or '').lower()
    
    if side in ['long', 'buy']:
        # Secuencia de targets para LONG
        # Se incluyen todas las bandas desde basis hasta upper_6
        sequence = [
            ('basis', 0), ('upper_1', 1), ('upper_2', 2), ('upper_3', 3),
            ('upper_4', 4), ('upper_5', 5), ('upper_6', 6)
        ]
        
        # 1. Intentar por zona
        for name, zone in sequence:
            if zone > current_zone:
                price = levels.get(name)
                if price is None: price = 0.0
                price = float(price)
                # Si el precio ya superó este target, buscar el siguiente
                if current_price < price:
                    return {
                        'target_name': name,
                        'target_price': price,
                        'target_zone': zone
                    }
        
        # 2. Fallback por precio si la zona está desfasada
        for name, zone in sequence:
            price = levels.get(name)
            if price is None: price = 0.0
            price = float(price)
            if price > current_price:
                 return {
                    'target_name': name,
                    'target_price': price,
                    'target_zone': zone
                }
                 
        return {
            'target_name': 'upper_6',
            'target_price': levels.get('upper_6', 0),
            'target_zone': 6
        }
    else:
        # Secuencia de targets para SHORT
        sequence = [
            ('basis', 0), ('lower_1', -1), ('lower_2', -2), ('lower_3', -3),
            ('lower_4', -4), ('lower_5', -5), ('lower_6', -6)
        ]
        
        # 1. Intentar por zona
        for name, zone in sequence:
            if zone < current_zone:
                price = levels.get(name, 0)
                if current_price > price:
                    return {
                        'target_name': name,
                        'target_price': price,
                        'target_zone': zone
                    }
                    
        # 2. Fallback por precio
        for name, zone in sequence:
            price = levels.get(name, 0)
            if price < current_price:
                 return {
                    'target_name': name,
                    'target_price': price,
                    'target_zone': zone
                }
                 
        return {
            'target_name': 'lower_6',
            'target_price': levels.get('lower_6', 0),
            'target_zone': -6
        }


def calculate_basis_confluence(
    price: float,
    basis_15m: float,
    basis_4h: float,
    basis_1d: float,
    direction: str,
) -> dict:
    """
    Calculate how many timeframes are aligned with the trade direction.
    Directly affects position sizing.

    Parameters
    ----------
    price : current close price
    basis_15m : VWMA basis from 15m timeframe
    basis_4h : VWMA basis from 4h timeframe
    basis_1d : VWMA basis from 1d timeframe
    direction : 'long' or 'short'

    Returns
    -------
    dict with confluence_score (1-3), sizing_multiplier, description
    """
    score = 0
    if direction == "long":
        if price > basis_15m:
            score += 1
        if price > basis_4h:
            score += 1
        if price > basis_1d:
            score += 1
    else:
        if price < basis_15m:
            score += 1
        if price < basis_4h:
            score += 1
        if price < basis_1d:
            score += 1

    # Ensure at least 1 (can happen if all bases are NaN/0)
    score = max(1, score)

    sizing_multiplier = {1: 0.70, 2: 0.85, 3: 1.00}

    return {
        "confluence_score": score,
        "sizing_multiplier": sizing_multiplier[score],
        "description": (
            "Alta confluencia — 3 TFs alineados"
            if score == 3
            else (
                "Confluencia media — 2 TFs alineados"
                if score == 2
                else "Baja confluencia — 1 TF alineado"
            )
        ),
    }
