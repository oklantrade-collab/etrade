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
    o = df["Open"] if "Open" in df.columns else (df["open"] if "open" in df.columns else c)

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
        "high_1d": round(float(h.iloc[-1]), 2),
        "low_1d": round(float(l.iloc[-1]), 2),
        "close_1d": round(float(c.iloc[-1]), 2),
        "open_1d": round(float(o.iloc[-1]), 2),
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


def validate_macro_1d_alignment(direction: str, metrics: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Regla Maestra 1: Tendencia Limpia 1D
    - CALL: EMA3 > EMA9 > EMA20 en gráfico de 1 Día.
    - PUT:  EMA3 < EMA9 < EMA20 en gráfico de 1 Día.
    """
    ema3 = float(metrics.get("ema3") or 0.0)
    ema9 = float(metrics.get("ema9") or 0.0)
    ema20 = float(metrics.get("ema20") or 0.0)

    if ema3 <= 0 or ema9 <= 0 or ema20 <= 0:
        return False, "Métricas 1D incompletas para validar alineación macro"

    d = direction.upper()
    if d in ("CALL", "BULLISH", "LONG"):
        if ema3 > ema9 > ema20:
            return True, f"Regla 1 CALL Válida: EMA3 (${ema3:.2f}) > EMA9 (${ema9:.2f}) > EMA20 (${ema20:.2f}) en 1D"
        return False, f"Regla 1 CALL No Cumplida: EMA3 (${ema3:.2f}), EMA9 (${ema9:.2f}), EMA20 (${ema20:.2f}) no alineadas al alza"
    else:
        if ema3 < ema9 < ema20:
            return True, f"Regla 1 PUT Válida: EMA3 (${ema3:.2f}) < EMA9 (${ema9:.2f}) < EMA20 (${ema20:.2f}) en 1D"
        return False, f"Regla 1 PUT No Cumplida: EMA3 (${ema3:.2f}), EMA9 (${ema9:.2f}), EMA20 (${ema20:.2f}) no alineadas a la baja"


def check_bollinger_reversal_trigger(
    direction: str,
    metrics: Dict[str, Any],
    df_1h: Optional[pd.DataFrame] = None
) -> Tuple[bool, str]:
    """
    Regla Maestra 2: Quiebre por Reversión en Banda Extrema de Bollinger (1D -> 1H)
    - CALL: Precio toca/perfora Banda Inferior 1D y aparece vela de giro alcista en 1H.
    - PUT:  Precio toca/perfora Banda Superior 1D y aparece vela de rechazo bajista en 1H.
    """
    bb_lower = float(metrics.get("bb_lower") or 0.0)
    bb_upper = float(metrics.get("bb_upper") or 0.0)
    low_1d = float(metrics.get("low_1d") or metrics.get("close_1d") or 0.0)
    high_1d = float(metrics.get("high_1d") or metrics.get("close_1d") or 0.0)
    close_1d = float(metrics.get("close_1d") or 0.0)

    d = direction.upper()
    if d in ("CALL", "BULLISH", "LONG"):
        # Toca o está a <= 1.5% de la Banda Inferior de 1D
        touches_lower = (low_1d <= bb_lower * 1.015) or (close_1d <= bb_lower * 1.015)
        if not touches_lower:
            return False, f"Regla 2 CALL: Precio (${close_1d:.2f}) no toca Banda Inferior 1D (${bb_lower:.2f})"

        # Si hay DataFrame 1H disponible, verificar vela de cambio de tendencia (giro)
        if df_1h is not None and len(df_1h) >= 2:
            c1h = df_1h["Close"] if "Close" in df_1h.columns else df_1h["close"]
            o1h = df_1h["Open"] if "Open" in df_1h.columns else df_1h["open"]
            l1h = df_1h["Low"] if "Low" in df_1h.columns else df_1h["low"]
            last_c = float(c1h.iloc[-1])
            last_o = float(o1h.iloc[-1])
            last_l = float(l1h.iloc[-1])
            body = abs(last_c - last_o)
            lower_wick = (min(last_c, last_o) - last_l) if min(last_c, last_o) > last_l else 0.0
            is_green_1h = last_c >= last_o
            is_hammer = lower_wick >= (body * 1.5) and lower_wick > 0

            if is_green_1h or is_hammer:
                return True, f"Regla 2 CALL Válida: Toca BB Inferior 1D (${bb_lower:.2f}) + Vela de giro alcista en 1H (${last_c:.2f})"
            return False, f"Regla 2 CALL: Toca BB Inferior 1D pero 1H aún no confirma vela de giro verde"

        return True, f"Regla 2 CALL Válida: Precio (${close_1d:.2f}) en zona de sobreventa Banda Inferior 1D (${bb_lower:.2f})"

    else:
        # Toca o está a <= 1.5% de la Banda Superior de 1D
        touches_upper = (high_1d >= bb_upper * 0.985) or (close_1d >= bb_upper * 0.985)
        if not touches_upper:
            return False, f"Regla 2 PUT: Precio (${close_1d:.2f}) no toca Banda Superior 1D (${bb_upper:.2f})"

        # Si hay DataFrame 1H disponible, verificar vela de rechazo bajista
        if df_1h is not None and len(df_1h) >= 2:
            c1h = df_1h["Close"] if "Close" in df_1h.columns else df_1h["close"]
            o1h = df_1h["Open"] if "Open" in df_1h.columns else df_1h["open"]
            h1h = df_1h["High"] if "High" in df_1h.columns else df_1h["high"]
            last_c = float(c1h.iloc[-1])
            last_o = float(o1h.iloc[-1])
            last_h = float(h1h.iloc[-1])
            body = abs(last_c - last_o)
            upper_wick = (last_h - max(last_c, last_o)) if last_h > max(last_c, last_o) else 0.0
            is_red_1h = last_c <= last_o
            is_shooting_star = upper_wick >= (body * 1.5) and upper_wick > 0

            if is_red_1h or is_shooting_star:
                return True, f"Regla 2 PUT Válida: Toca BB Superior 1D (${bb_upper:.2f}) + Vela de rechazo bajista en 1H (${last_c:.2f})"
            return False, f"Regla 2 PUT: Toca BB Superior 1D pero 1H aún no confirma vela de rechazo roja"

        return True, f"Regla 2 PUT Válida: Precio (${close_1d:.2f}) en zona de sobrecompra Banda Superior 1D (${bb_upper:.2f})"


def check_ema20_pullback_trigger(
    direction: str,
    metrics: Dict[str, Any],
    df_1h: Optional[pd.DataFrame] = None
) -> Tuple[bool, str]:
    """
    Regla Maestra 3: Rebote o Retesteo en EMA20 Diaria
    - CALL: En tendencia alcista (EMA20 >= EMA50), retroceso a EMA20 con vela de soporte en 1H.
    - PUT:  En tendencia bajista (EMA20 <= EMA50), rebote a EMA20 con vela de rechazo en 1H.
    """
    ema20 = float(metrics.get("ema20") or 0.0)
    ema50 = float(metrics.get("ema50") or 0.0)
    close_1d = float(metrics.get("close_1d") or metrics.get("ema3") or 0.0)

    if ema20 <= 0:
        return False, "EMA20 no disponible"

    dist_pct = abs(close_1d - ema20) / ema20 * 100.0
    d = direction.upper()

    if d in ("CALL", "BULLISH", "LONG"):
        # Contexto alcista: EMA20 >= EMA50 o precio sobre EMA50
        is_bull_context = (ema20 >= ema50) or (close_1d >= ema50 * 0.98)
        is_at_ema20 = dist_pct <= 1.8 and close_1d >= ema20 * 0.985
        if is_bull_context and is_at_ema20:
            if df_1h is not None and len(df_1h) >= 2:
                c1h = df_1h["Close"] if "Close" in df_1h.columns else df_1h["close"]
                o1h = df_1h["Open"] if "Open" in df_1h.columns else df_1h["open"]
                if float(c1h.iloc[-1]) >= float(o1h.iloc[-1]):
                    return True, f"Regla 3 CALL Válida: Soporte en EMA20 Diaria (${ema20:.2f}) con vela verde en 1H"
                return False, f"Regla 3 CALL: En EMA20 Diaria (${ema20:.2f}) pero 1H aún no muestra rebote"
            return True, f"Regla 3 CALL Válida: Soporte en EMA20 Diaria (${ema20:.2f})"
        return False, f"Regla 3 CALL No Cumplida (Dist EMA20: {dist_pct:.1f}%)"

    else:
        # Contexto bajista: EMA20 <= EMA50 o precio bajo EMA50
        is_bear_context = (ema20 <= ema50) or (close_1d <= ema50 * 1.02)
        is_at_ema20 = dist_pct <= 1.8 and close_1d <= ema20 * 1.015
        if is_bear_context and is_at_ema20:
            if df_1h is not None and len(df_1h) >= 2:
                c1h = df_1h["Close"] if "Close" in df_1h.columns else df_1h["close"]
                o1h = df_1h["Open"] if "Open" in df_1h.columns else df_1h["open"]
                if float(c1h.iloc[-1]) <= float(o1h.iloc[-1]):
                    return True, f"Regla 3 PUT Válida: Rechazo en resistencia EMA20 Diaria (${ema20:.2f}) con vela roja en 1H"
                return False, f"Regla 3 PUT: En EMA20 Diaria (${ema20:.2f}) pero 1H aún no confirma rechazo"
            return True, f"Regla 3 PUT Válida: Retesteo a resistencia EMA20 Diaria (${ema20:.2f})"
        return False, f"Regla 3 PUT No Cumplida (Dist EMA20: {dist_pct:.1f}%)"


def check_structural_veto_zones(
    direction: str,
    metrics: Dict[str, Any],
    current_price: float
) -> Tuple[bool, str]:
    """
    Regla Maestra 4: Zonas de Veto Estructural (No-Trade Veto Zones)
    - VETO CALL: Precio cotiza debajo de EMA20 diaria y a <= 1.5% de ella (resistencia de alto riesgo de reversión).
    - VETO PUT:  Precio cotiza encima de EMA20 diaria y a <= 1.5% de ella (soporte de alto riesgo de rebote).
    - VETO CALL: Deep Bear Winter (Precio << EMA50 < EMA200).
    - VETO AMBOS: Compresión lateral extrema (Squeeze / Chop sin tendencia).
    """
    p = current_price if current_price > 0 else float(metrics.get("close_1d") or 1.0)
    ema20 = float(metrics.get("ema20") or 0.0)
    ema50 = float(metrics.get("ema50") or 0.0)
    ema200 = float(metrics.get("ema200") or 0.0)
    bandwidth = float(metrics.get("bb_bandwidth_pct") or 20.0)

    # Veto Compresión Lateral
    if bandwidth < 10.0 and ema20 > 0 and abs(p - ema20) / ema20 * 100.0 < 1.0:
        return True, f"VETO ESTRUCTURAL: Squeeze/Compresión Lateral extrema ({bandwidth:.1f}% bandwidth). Prohibido comprar opciones direccionales (Theta decay)."

    d = direction.upper()
    if d in ("CALL", "BULLISH", "LONG"):
        # Veto 1: Bajo EMA20 a <= 1.5% (muro de resistencia diario de reversión)
        if ema20 > 0 and p < ema20:
            dist_to_ema20_pct = ((ema20 - p) / p) * 100.0
            if dist_to_ema20_pct <= 1.5:
                return True, f"VETO CALL: Precio (${p:.2f}) inmediatamente bajo EMA20 Diaria (${ema20:.2f}, -{dist_to_ema20_pct:.2f}%). Alto riesgo de rechazo en resistencia."

        # Veto 2: Deep Bear Winter
        if ema50 < ema200 and p < ema200 and ema200 > 0:
            dist_200 = ((ema200 - p) / p) * 100.0
            if dist_200 >= 15.0 or (p < ema50 and ema20 < ema50):
                return True, f"VETO CALL: DEEP_BEAR_WINTER secular (-{dist_200:.1f}% vs EMA200). Prohibido comprar CALLs en activos en caída libre institucional."

        return False, ""

    else:
        # Veto 1: Sobre EMA20 a <= 1.5% (piso de soporte diario de rebote)
        if ema20 > 0 and p > ema20:
            dist_to_ema20_pct = ((p - ema20) / p) * 100.0
            if dist_to_ema20_pct <= 1.5:
                return True, f"VETO PUT: Precio (${p:.2f}) inmediatamente sobre EMA20 Diaria (${ema20:.2f}, +{dist_to_ema20_pct:.2f}%). Alto riesgo de rebote en soporte."

        return False, ""


def evaluate_structural_regime(
    ticker: str,
    current_price: float,
    df_1d: Optional[pd.DataFrame] = None,
    df_intraday: Optional[pd.DataFrame] = None,
    vwap_intraday: Optional[float] = None,
    df_1h: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Función Universal de Evaluación de Régimen Estructural (Universal para Stocks y Opciones).
    
    Clasifica en los 4 Regímenes Maestros e integra las 4 Reglas Maestras de Opciones:
    - Regla 1: Tendencia Limpia 1D (CALL: EMA3>EMA9>EMA20 / PUT: EMA3<EMA9<EMA20).
    - Regla 2: Quiebre por Reversión en Bandas de Bollinger (1D -> 1H).
    - Regla 3: Pullback o Retesteo a EMA20 Diaria con confirmación 1H.
    - Regla 4: Zonas de Veto Estructural (muro EMA20 a <=1.5%, Deep Bear Winter, Squeeze).
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

    df_1h_to_use = df_1h if df_1h is not None else df_intraday

    # ─────────────────────────────────────────────────────────────
    # EVALUACIÓN SISTÉMICA DE REGLAS MAESTRAS DE ENTRADA (1, 2, 3, 4)
    # ─────────────────────────────────────────────────────────────
    # 1. CALLs:
    is_call_vetoed, call_veto_reason = check_structural_veto_zones("CALL", m, price)
    call_setup_type = "NONE"
    can_enter_call = False

    if is_call_vetoed:
        can_enter_call = False
    else:
        is_r1_call, r1_call_msg = validate_macro_1d_alignment("CALL", m)
        is_r2_call, r2_call_msg = check_bollinger_reversal_trigger("CALL", m, df_1h=df_1h_to_use)
        is_r3_call, r3_call_msg = check_ema20_pullback_trigger("CALL", m, df_1h=df_1h_to_use)

        if is_r1_call:
            can_enter_call = True
            call_setup_type = "RULE_1_TREND_EXPANSION"
        elif is_r2_call:
            can_enter_call = True
            call_setup_type = "RULE_2_BOLLINGER_REVERSAL"
        elif is_r3_call:
            can_enter_call = True
            call_setup_type = "RULE_3_EMA20_PULLBACK"
        else:
            can_enter_call = False
            call_veto_reason = "CALL bloqueado: Sin alineación 1D (EMA3>EMA9>EMA20) ni setup de quiebre (BB Inferior / EMA20)"

    # 2. PUTs:
    is_put_vetoed, put_veto_reason = check_structural_veto_zones("PUT", m, price)
    put_setup_type = "NONE"
    can_enter_put = False

    if is_put_vetoed:
        can_enter_put = False
    else:
        is_r1_put, r1_put_msg = validate_macro_1d_alignment("PUT", m)
        is_r2_put, r2_put_msg = check_bollinger_reversal_trigger("PUT", m, df_1h=df_1h_to_use)
        is_r3_put, r3_put_msg = check_ema20_pullback_trigger("PUT", m, df_1h=df_1h_to_use)

        if is_r1_put:
            can_enter_put = True
            put_setup_type = "RULE_1_TREND_EXPANSION"
        elif is_r2_put:
            can_enter_put = True
            put_setup_type = "RULE_2_BOLLINGER_REVERSAL"
        elif is_r3_put:
            can_enter_put = True
            put_setup_type = "RULE_3_EMA20_REJECTION"
        else:
            can_enter_put = False
            put_veto_reason = "PUT bloqueado: Sin alineación 1D (EMA3<EMA9<EMA20) ni setup de quiebre (BB Superior / EMA20)"

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
        "can_enter_call": can_enter_call,
        "can_enter_put": can_enter_put,
        "call_veto_reason": call_veto_reason if not can_enter_call else None,
        "put_veto_reason": put_veto_reason if not can_enter_put else None,
        "call_setup_type": call_setup_type,
        "put_setup_type": put_setup_type,
        "is_call_vetoed_by_ema20": (price < ema20 and ((ema20 - price) / price) <= 0.015),
        "is_put_vetoed_by_ema20": (price > ema20 and ((price - ema20) / price) <= 0.015),
        "macro_1d_aligned_call": (ema3 > ema9 and ema9 > ema20),
        "macro_1d_aligned_put": (ema3 < ema9 and ema9 < ema20),
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
