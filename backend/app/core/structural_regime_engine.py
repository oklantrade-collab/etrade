"""
eTrade v7.0 — STRUCTURAL REGIME ENGINE (Universal para Opciones y Stocks)
========================================================================
Motor central de clasificación técnica basado en la estructura de Medias Móviles
Diarias (EMA 3, 9, 20, 50, 200), Bandas de Bollinger 1D y Microestructura (VWAP, ATR).

Diferencia de raíz casos como:
- DIS: BULL_TREND_EXPANSION (EMA 3 > 9 > 20 > 50 > 200). Vía libre alcista a Bollinger Superior.
- AAL: COUNTER_TREND_BOUNCE (Precio < EMA20 < EMA50 < EMA200). Rebote táctico contra el muro de la EMA20.
- DEEP_BEAR_WINTER: Precio << EMA50 < EMA200 (Death Cross secular, riesgo de capital atrapado por meses).
- COMPRESSION_CHOP: Squeeze lateral sin volumen ni catalizador (prohibido operar opciones direccionales).
"""

from __future__ import annotations

import time
import math
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np

from app.core.logger import log_info, log_warning, log_debug

MODULE = "STRUCTURAL_REGIME"

# Cache de métricas 1D en memoria: { clean_ticker: (timestamp, metrics_dict) }
_REGIME_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 900.0  # 15 minutos de persistencia en memoria


def _calculate_indicators_from_df(df: pd.DataFrame, current_price: float) -> Dict[str, Any]:
    """Calcula la jerarquía completa de EMAs, Bollinger y ATR a partir de un DataFrame de 1D."""
    if df is None or len(df) < 20:
        return {}

    c = df["Close"] if "Close" in df.columns else (df["close"] if "close" in df.columns else df.iloc[:, -2])
    h = df["High"] if "High" in df.columns else (df["high"] if "high" in df.columns else c)
    l = df["Low"] if "Low" in df.columns else (df["low"] if "low" in df.columns else c)

    # EMAs
    ema3 = float(c.ewm(span=3, adjust=False).mean().iloc[-1])
    ema9 = float(c.ewm(span=9, adjust=False).mean().iloc[-1])
    ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(c.ewm(span=50, adjust=False).mean().iloc[-1]) if len(df) >= 40 else ema20
    ema200 = float(c.ewm(span=200, adjust=False).mean().iloc[-1]) if len(df) >= 150 else ema50

    # Bollinger Bands (20, 2)
    sma20 = float(c.rolling(20).mean().iloc[-1])
    std20 = float(c.rolling(20).std().iloc[-1])
    bb_upper = float(sma20 + (2.0 * std20))
    bb_lower = float(sma20 - (2.0 * std20))
    bb_bandwidth_pct = ((bb_upper - bb_lower) / sma20 * 100.0) if sma20 > 0 else 0.0

    # ATR 14
    tr1 = h - l
    tr2 = (h - c.shift(1)).abs()
    tr3 = (l - c.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1]) if len(df) >= 14 else float(tr1.iloc[-1])

    # Pendiente de EMA200 (ultimas 5 velas)
    ema200_series = c.ewm(span=200, adjust=False).mean()
    if len(ema200_series) >= 6:
        ema200_slope = (float(ema200_series.iloc[-1]) - float(ema200_series.iloc[-6])) / float(ema200_series.iloc[-6])
    else:
        ema200_slope = 0.0

    return {
        "ema3": round(ema3, 2),
        "ema9": round(ema9, 2),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema200": round(ema200, 2),
        "bb_basis": round(sma20, 2),
        "bb_upper": round(bb_upper, 2),
        "bb_lower": round(bb_lower, 2),
        "bb_bandwidth_pct": round(bb_bandwidth_pct, 1),
        "atr_1d": round(atr14, 2),
        "ema200_slope": round(ema200_slope, 4),
        "candles_count": len(df),
    }


def fetch_daily_metrics(ticker: str, current_price: float, df_1d: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Obtiene las métricas diarias usando cache en memoria de 15 minutos."""
    clean_ticker = ticker.replace("/", "").replace(".", "").upper().strip()
    now = time.time()

    # Revisar cache
    cached = _REGIME_CACHE.get(clean_ticker)
    if cached and (now - cached[0] < CACHE_TTL_SECONDS):
        return cached[1]

    # Si se proporciona df_1d externo, usarlo directamente
    if df_1d is not None and len(df_1d) >= 20:
        metrics = _calculate_indicators_from_df(df_1d, current_price)
        if metrics:
            _REGIME_CACHE[clean_ticker] = (now, metrics)
            return metrics

    # Descargar de yfinance (period='250d', interval='1d')
    try:
        import yfinance as yf
        t = yf.Ticker(clean_ticker)
        df_yf = t.history(period="250d", interval="1d")
        if df_yf is not None and len(df_yf) >= 20:
            metrics = _calculate_indicators_from_df(df_yf, current_price)
            if metrics:
                _REGIME_CACHE[clean_ticker] = (now, metrics)
                return metrics
    except Exception as e:
        log_warning(MODULE, f"Error descargando datos 1D para {clean_ticker}: {e}")

    # Fallback si no hay datos
    p = current_price if current_price > 0 else 10.0
    fallback = {
        "ema3": p, "ema9": p, "ema20": p, "ema50": p, "ema200": p,
        "bb_basis": p, "bb_upper": round(p * 1.15, 2), "bb_lower": round(p * 0.85, 2),
        "bb_bandwidth_pct": 30.0, "atr_1d": round(p * 0.03, 2), "ema200_slope": 0.0,
        "candles_count": 0,
    }
    _REGIME_CACHE[clean_ticker] = (now, fallback)
    return fallback


def evaluate_structural_regime(
    ticker: str,
    current_price: float,
    df_1d: Optional[pd.DataFrame] = None,
    df_intraday: Optional[pd.DataFrame] = None,
    vwap_intraday: Optional[float] = None
) -> Dict[str, Any]:
    """
    Función Universal de Evaluación de Régimen Estructural (Universal para Stocks y Opciones).
    
    Clasifica en los 4 Regímenes Maestros:
    1. BULL_TREND_EXPANSION (Caso DIS): EMA3 > EMA9 > EMA20 y Precio > EMA50. Vía libre hacia BB Superior.
    2. COUNTER_TREND_BOUNCE (Caso AAL): Precio < EMA20 < EMA50 < EMA200 rebotando. Muro rígido en EMA20.
    3. DEEP_BEAR_WINTER: Precio << EMA50 < EMA200 (>15% bajo EMA200). Exclusión total de Swing y Calls.
    4. COMPRESSION_CHOP: Bandas comprimidas (< 10% ancho) sin tendencia definida.
    """
    m = fetch_daily_metrics(ticker, current_price, df_1d)
    price = current_price if current_price > 0 else m.get("ema3", 10.0)

    ema3 = m.get("ema3", price)
    ema9 = m.get("ema9", price)
    ema20 = m.get("ema20", price)
    ema50 = m.get("ema50", price)
    ema200 = m.get("ema200", price)
    bb_upper = m.get("bb_upper", price * 1.15)
    bb_lower = m.get("bb_lower", price * 0.85)
    bb_basis = m.get("bb_basis", ema20)
    atr = m.get("atr_1d", price * 0.03)

    # Distancias porcentuales clave
    dist_to_ema20_pct = round(((ema20 - price) / price * 100.0), 2) if price > 0 else 0.0
    dist_to_ema50_pct = round(((ema50 - price) / price * 100.0), 2) if price > 0 else 0.0
    dist_to_ema200_pct = round(((ema200 - price) / price * 100.0), 2) if price > 0 else 0.0
    room_to_bb_upper_pct = round(((bb_upper - price) / price * 100.0), 2) if price > 0 else 0.0

    # Sesgo de VWAP si se suministra o estima
    vwap_val = vwap_intraday or price
    vwap_bias = "bullish" if price >= vwap_val else "bearish"

    # Evaluaciones lógicas de jerarquía
    is_ema3_above_ema9 = ema3 > ema9
    is_ema9_above_ema20 = ema9 > ema20
    is_ema20_above_ema50 = ema20 > ema50
    is_golden_macro = ema50 > ema200
    is_death_cross = ema50 < ema200
    is_price_above_ema200 = price >= ema200
    is_price_below_ema200 = price < ema200

    # -------------------------------------------------------------
    # REGIMEN 3: DEEP BEAR WINTER (Candado de Exclusión Macro)
    # -------------------------------------------------------------
    # Si el precio cotiza > 15% por debajo de la EMA200 y EMA50 < EMA200,
    # el activo está en un invierno bajista institucional. Revertir demora meses.
    is_deep_bear_excluded = (
        is_death_cross and is_price_below_ema200 and (dist_to_ema200_pct >= 15.0 or (price < ema50 and ema20 < ema50))
    )

    # -------------------------------------------------------------
    # REGIMEN 1: BULL TREND EXPANSION (Caso DIS)
    # -------------------------------------------------------------
    # Alineación alcista perfecta: EMA3 > EMA9 > EMA20 y precio > EMA50
    is_bull_expansion = (
        is_ema3_above_ema9 and is_ema9_above_ema20 and (price >= ema20 or price >= ema50) and (is_price_above_ema200 or is_golden_macro)
    )

    # -------------------------------------------------------------
    # REGIMEN 2: COUNTER TREND BOUNCE (Caso AAL)
    # -------------------------------------------------------------
    # Viene de estructura bajista (EMA20 < EMA50 o Precio < EMA200) y está rebotando contra EMA20
    is_counter_trend = (
        not is_bull_expansion and (price <= ema20 * 1.02 or ema20 < ema50) and (ema3 >= ema9 or price > bb_lower)
    )

    # -------------------------------------------------------------
    # REGIMEN 4: COMPRESSION CHOP (Lateral / Squeeze)
    # -------------------------------------------------------------
    is_compression = (
        m.get("bb_bandwidth_pct", 20.0) < 12.0 and abs(dist_to_ema20_pct) < 1.5
    )

    # Determinación y Asignación de Acción Táctica
    if is_deep_bear_excluded:
        regime_code = "DEEP_BEAR_WINTER"
        regime_label = f"⛔ DEEP BEAR WINTER (-{dist_to_ema200_pct:.1f}% vs EMA200)"
        is_swing_eligible = False
        tactical_action = "EXCLUDED_CAPITAL_SHIELD"
        recommended_strategy = "bear_put_spread"
        target_ceiling = ema20
        target_wall = ema50
        action_note = "Invierno bajista secular. Prohibido comprar acciones para Swing o CALLs de medio plazo. Atrapa capital por meses."

    elif is_bull_expansion and not is_compression:
        regime_code = "BULL_TREND_EXPANSION"
        regime_label = f"🟢 BULL EXPANSION (EMA 3>9>20>50>200, +{room_to_bb_upper_pct:.1f}% A BB)"
        is_swing_eligible = True
        tactical_action = "SWING_LONG"
        recommended_strategy = "bull_call_spread"
        target_ceiling = bb_upper
        target_wall = ema9  # Soporte dinámico para trailing
        action_note = "Tendencia alcista institucional libre. Acompañar hacia Bollinger Superior con Bull Call Spread o Long Call (DTE 14-21d)."

    elif is_counter_trend:
        regime_code = "COUNTER_TREND_BOUNCE"
        # Si está a menos de 1.0% de la EMA20 diaria, la resistencia está encima
        if abs(dist_to_ema20_pct) <= 1.2 and price <= ema20 * 1.01:
            tactical_action = "REJECTION_PUT_WATCH"
            recommended_strategy = "bear_put_spread"
            regime_label = f"🟡 REBOTE EN TECHO EMA20 (${ema20:.2f})"
            action_note = f"Precio tocando el muro de la EMA20 diaria (${ema20:.2f}). Alerta de rechazo con mecha para entrada en BEAR PUT SPREAD."
        else:
            tactical_action = "TACTICAL_SCALP_INTRADAY"
            recommended_strategy = "tactical_intraday_call"
            regime_label = f"🟡 REBOTE TÁCTICO 1D (Target EMA20: ${ema20:.2f})"
            action_note = f"Rebote contra la tendencia bajista 1D. Entrada LONG solo a 1ra hora con TAKE PROFIT OBLIGATORIO en EMA20 (${ema20:.2f}). No Swing."

        is_swing_eligible = False
        target_ceiling = ema20
        target_wall = ema20

    elif is_compression:
        regime_code = "COMPRESSION_CHOP"
        regime_label = "⚪ SQUEEZE / COMPRESIÓN LATERAL"
        is_swing_eligible = False
        tactical_action = "CHOP_WAIT"
        recommended_strategy = "none"
        target_ceiling = bb_upper
        target_wall = bb_lower
        action_note = "Mercado en compresión sin dirección clara. Prohibido comprar opciones direccionales (Theta decay)."

    else:
        regime_code = "NEUTRAL_MIXED"
        regime_label = "⚪ ESTRUCTURA MIXTA (MONITOREANDO)"
        is_swing_eligible = False
        tactical_action = "MONITORING"
        recommended_strategy = "outright"
        target_ceiling = bb_upper
        target_wall = ema20
        action_note = "Estructura intermedia sin señal pura. Monitorear catalizadores."

    return {
        "ticker": ticker.upper(),
        "current_price": round(price, 2),
        "regime_code": regime_code,
        "regime_label": regime_label,
        "is_deep_bear_excluded": is_deep_bear_excluded,
        "is_swing_eligible": is_swing_eligible,
        "tactical_action": tactical_action,
        "recommended_option_strategy": recommended_strategy,
        "action_note": action_note,
        "key_levels_1d": {
            "ema3": ema3,
            "ema9": ema9,
            "ema20": ema20,
            "ema50": ema50,
            "ema200": ema200,
            "bb_basis": bb_basis,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
        },
        "target_ceiling": round(target_ceiling, 2),
        "target_resistance_wall": round(target_wall, 2),
        "room_to_resistance_pct": dist_to_ema20_pct,
        "room_to_bb_upper_pct": room_to_bb_upper_pct,
        "dist_to_ema200_pct": dist_to_ema200_pct,
        "atr_1d": round(atr, 2),
        "vwap_bias": vwap_bias,
        "bandwidth_pct": m.get("bb_bandwidth_pct", 20.0),
    }
