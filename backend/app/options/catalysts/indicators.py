"""Indicadores canonicos para el motor de catalizadores:
- ADX / +DI / -DI con suavizado Wilder (periodo 14).
- ATR (Average True Range).
- Basis de Fibonacci Bollinger Bands (SMA20 + bandas 1..6).
- Calculo de Delta simetrico para el buffer de apertura SIPV 1h.
"""
from __future__ import annotations

import math
from typing import Any
import numpy as np
import pandas as pd


def _safe_series(df: pd.DataFrame, col_name: str) -> pd.Series:
    for candidate in (col_name.lower(), col_name.capitalize(), col_name.upper()):
        if candidate in df.columns:
            return pd.to_numeric(df[candidate], errors="coerce").astype(float)
    return pd.Series(dtype=float)


def calculate_adx_wilder(df: pd.DataFrame, period: int = 14) -> dict[str, Any]:
    """Calcula ADX, +DI y -DI usando el suavizado autentico de Wilder (alpha = 1/period).

    Devuelve:
        {
            "adx": float,
            "plus_di": float,
            "minus_di": float,
            "adx_rising": bool,
            "direction": "bullish" | "bearish" | "neutral",
            "di_spread": float
        }
    """
    if df is None or len(df) < period + 2:
        return {
            "adx": 0.0,
            "plus_di": 0.0,
            "minus_di": 0.0,
            "adx_rising": False,
            "direction": "neutral",
            "di_spread": 0.0,
        }

    high = _safe_series(df, "high")
    low = _safe_series(df, "low")
    close = _safe_series(df, "close")

    if high.empty or low.empty or close.empty:
        return {
            "adx": 0.0,
            "plus_di": 0.0,
            "minus_di": 0.0,
            "adx_rising": False,
            "direction": "neutral",
            "di_spread": 0.0,
        }

    prev_close = close.shift(1).fillna(close)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Suavizado de Wilder: ewm con alpha = 1 / period
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    atr_safe = atr + 1e-9

    plus_di = 100.0 * pd.Series(plus_dm, index=df.index).ewm(alpha=1.0 / period, adjust=False).mean() / atr_safe
    minus_di = 100.0 * pd.Series(minus_dm, index=df.index).ewm(alpha=1.0 / period, adjust=False).mean() / atr_safe

    dx = 100.0 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
    adx_series = dx.ewm(alpha=1.0 / period, adjust=False).mean()

    curr_adx = float(adx_series.iloc[-1])
    curr_plus = float(plus_di.iloc[-1])
    curr_minus = float(minus_di.iloc[-1])

    prev_adx = float(adx_series.iloc[-2]) if len(adx_series) > 1 else curr_adx
    adx_rising = bool(curr_adx > prev_adx)

    di_spread = round(curr_plus - curr_minus, 2)
    if curr_plus > curr_minus:
        direction = "bullish"
    elif curr_minus > curr_plus:
        direction = "bearish"
    else:
        direction = "neutral"

    return {
        "adx": round(curr_adx, 2),
        "plus_di": round(curr_plus, 2),
        "minus_di": round(curr_minus, 2),
        "adx_rising": adx_rising,
        "direction": direction,
        "di_spread": di_spread,
    }


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calcula el ATR corriente de un DataFrame."""
    if df is None or len(df) < 2:
        return 0.0
    high = _safe_series(df, "high")
    low = _safe_series(df, "low")
    close = _safe_series(df, "close")
    prev_close = close.shift(1).fillna(close)

    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    atr_series = tr.rolling(period, min_periods=1).mean()
    val = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
    return max(0.001, round(val, 4))


def calculate_fibonacci_basis(df_1h: pd.DataFrame, current_price: float) -> dict[str, Any]:
    """Calcula el BASIS de Fibonacci Bollinger Bands en temporalidad de 1H y las bandas 1..6."""
    if df_1h is None or len(df_1h) < 10 or current_price <= 0:
        return {
            "basis": current_price,
            "upper_band": current_price * 1.02,
            "lower_band": current_price * 0.98,
            "upper_5": current_price * 1.03,
            "lower_5": current_price * 0.97,
            "upper_6": current_price * 1.04,
            "lower_6": current_price * 0.96,
            "atr_1h": current_price * 0.005,
            "price_vs_basis": "at_basis",
        }

    close = _safe_series(df_1h, "close")
    basis = float(close.rolling(20, min_periods=1).mean().iloc[-1])
    std = float(close.rolling(20, min_periods=1).std().iloc[-1])
    if math.isnan(std) or std == 0:
        std = current_price * 0.005

    atr_1h = calculate_atr(df_1h, period=14)

    # Ratios de Fibonacci sobre la desviacion estandar
    upper_band = basis + (2.0 * std)
    lower_band = basis - (2.0 * std)
    upper_5 = basis + (2.618 * std)
    lower_5 = basis - (2.618 * std)
    upper_6 = basis + (3.618 * std)
    lower_6 = basis - (3.618 * std)

    if current_price > basis * 1.0005:
        relation = "above_basis"
    elif current_price < basis * 0.9995:
        relation = "below_basis"
    else:
        relation = "at_basis"

    return {
        "basis": round(basis, 4),
        "upper_band": round(upper_band, 4),
        "lower_band": round(lower_band, 4),
        "upper_5": round(upper_5, 4),
        "lower_5": round(lower_5, 4),
        "upper_6": round(upper_6, 4),
        "lower_6": round(lower_6, 4),
        "atr_1h": round(atr_1h, 4),
        "price_vs_basis": relation,
    }


def calculate_sipv_delta_buffer(price: float, atr_14: float) -> float:
    """Calcula el buffer Delta simetrico para la apertura de vela 1H SIPV.

    Delta = max(0.05 * atr_14, 0.001 * price).
    Evita falsos sesgos alcistas o bajistas en aperturas planas.
    """
    if atr_14 > 0:
        return max(0.05 * atr_14, 0.001 * max(price, 1.0))
    return max(0.01, 0.001 * max(price, 1.0))
