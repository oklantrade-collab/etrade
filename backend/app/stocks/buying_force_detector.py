"""
eTrade v6.0 — BUYING FORCE & 1H PULLBACK/CLIMAX DETECTOR FOR STOCKS
==================================================================
Motor institucional para detección de:
1. Alineación Macro 1D (EMA20 > EMA50 > EMA200).
2. Buying Force Score (0 a 100): Dinamismo, ADR, RVOL y absorción.
3. Puntos de Entrada Duales en 1 HORA:
   - Ruta A: Pullback dinámico a EMA3, EMA9 o EMA20 en 1H.
   - Ruta B: Rebote Clímax en LOWER_5 o LOWER_6 en 1H.
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from app.core.logger import log_info, log_warning, log_error
from app.strategy.panic_recovery_gate import calculate_fibonacci_bands

MODULE = "BUYING_FORCE_DETECTOR"


def _safe_col(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Retorna la serie de la columna de forma segura insensible a mayúsculas/minúsculas."""
    if col_name in df.columns:
        return df[col_name].astype(float)
    cap = col_name.capitalize()
    if cap in df.columns:
        return df[cap].astype(float)
    upper = col_name.upper()
    if upper in df.columns:
        return df[upper].astype(float)
    return pd.Series(dtype=float)


def evaluate_macro_1d_alignment(df_1d: Optional[pd.DataFrame]) -> dict:
    """
    Verifica la condición macro institucional innegociable en 1D:
    EMA20 > EMA50 > EMA200.
    """
    if df_1d is None or len(df_1d) < 200:
        # Si no hay 200 velas cerradas completas, intentar verificar con al menos 50 velas
        if df_1d is not None and len(df_1d) >= 50:
            close = _safe_col(df_1d, 'close')
            ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
            is_aligned = ema20 > ema50
            return {
                'aligned': is_aligned,
                'ema20': round(ema20, 2),
                'ema50': round(ema50, 2),
                'ema200': 0.0,
                'candles': len(df_1d),
                'reason': 'EMA20 > EMA50 (Velas parciales < 200)' if is_aligned else 'EMA20 <= EMA50'
            }

        return {
            'aligned': False,
            'ema20': 0.0,
            'ema50': 0.0,
            'ema200': 0.0,
            'candles': len(df_1d) if df_1d is not None else 0,
            'reason': 'Datos 1D insuficientes (< 50 velas)'
        }

    try:
        close = _safe_col(df_1d, 'close')
        ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

        aligned = (ema20 > ema50 > ema200)
        return {
            'aligned': aligned,
            'ema20': round(ema20, 2),
            'ema50': round(ema50, 2),
            'ema200': round(ema200, 2),
            'candles': len(df_1d),
            'reason': 'EMA20 > EMA50 > EMA200 OK ✅' if aligned else f'Desalineadas: 20={ema20:.2f}, 50={ema50:.2f}, 200={ema200:.2f}'
        }
    except Exception as e:
        log_error(MODULE, f"Error evaluando Macro 1D: {e}")
        return {
            'aligned': False,
            'ema20': 0.0,
            'ema50': 0.0,
            'ema200': 0.0,
            'candles': 0,
            'reason': f"Excepción: {e}"
        }


def detect_candle_absorption(
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float
) -> dict:
    """
    Detecta si una vela presenta absorción institucional / rechazo de precios bajos:
    1. Mecha inferior grande (>= 35% del rango total de la vela).
    2. O cuerpo verde sólido cerrando en el tercio superior de la vela.
    """
    candle_range = max(1e-6, high_p - low_p)
    lower_wick = max(0.0, min(open_p, close_p) - low_p)
    lower_wick_pct = (lower_wick / candle_range) * 100.0

    is_green = (close_p >= open_p)
    close_position_pct = ((close_p - low_p) / candle_range) * 100.0

    has_wick_absorption = lower_wick_pct >= 35.0
    has_bullish_close = is_green and (close_position_pct >= 60.0)
    absorption = has_wick_absorption or has_bullish_close

    return {
        'has_absorption': absorption,
        'lower_wick_pct': round(lower_wick_pct, 1),
        'is_green': is_green,
        'close_position_pct': round(close_position_pct, 1),
        'reason': (
            f"Mecha={lower_wick_pct:.1f}% ({'Absorción' if has_wick_absorption else 'Normal'}) | "
            f"Cierre={'Verde' if is_green else 'Rojo'} en {close_position_pct:.0f}% del rango"
        )
    }


def calculate_buying_force_score(
    adr_pct: float,
    consumed_pct: float,
    rvol_1h: float,
    df_1h: Optional[pd.DataFrame],
    macro_aligned: bool,
    bandwidth_1h: float = 3.0,
) -> dict:
    """
    Calcula el Buying Force Score (0 a 100).
    Evalúa la fuerza de compra real para descartar tickers mediocres/aletargados
    y seleccionar las acciones más dinámicas con alto movimiento de crecimiento en el precio.
    """
    score = 40  # Base

    # 1. Macro 1D Alineada (+15 pts o penalización severa -40)
    if macro_aligned:
        score += 15
    else:
        score -= 40

    # 2. ADR 14D (Volatilidad y Dinamismo Diario) (Piso 3.5%)
    if adr_pct >= 6.0:
        score += 20
    elif adr_pct >= 4.5:
        score += 15
    elif adr_pct >= 3.5:
        score += 8
    elif adr_pct < 3.0:
        score -= 25

    # 3. Espacio Remanente del ADR
    if consumed_pct < 50.0:
        score += 15
    elif consumed_pct < 75.0:
        score += 8
    elif consumed_pct >= 85.0:
        score -= 20

    # 4. Combustible Institucional RVOL en 1H
    if rvol_1h >= 2.0:
        score += 20
    elif rvol_1h >= 1.5:
        score += 15
    elif rvol_1h >= 1.2:
        score += 8
    elif rvol_1h < 0.8:
        score -= 15

    # 5. Anti-Compresión (Bandwidth 1H)
    if bandwidth_1h >= 4.0:
        score += 10
    elif bandwidth_1h < 1.8:
        score -= 15

    # 6. Estructura y Pendiente Horaria (1H)
    absorption_info = {'has_absorption': False, 'lower_wick_pct': 0.0}
    ema3_slope = 0.0
    ema3_above_ema9 = False

    if df_1h is not None and len(df_1h) >= 10:
        try:
            close_1h = _safe_col(df_1h, 'close')
            open_1h = _safe_col(df_1h, 'open')
            high_1h = _safe_col(df_1h, 'high')
            low_1h = _safe_col(df_1h, 'low')

            ema3_series = close_1h.ewm(span=3, adjust=False).mean()
            ema9_series = close_1h.ewm(span=9, adjust=False).mean()

            ema3_curr = float(ema3_series.iloc[-1])
            ema3_prev = float(ema3_series.iloc[-2]) if len(ema3_series) > 1 else ema3_curr
            ema9_curr = float(ema9_series.iloc[-1])

            ema3_slope = (ema3_curr - ema3_prev) / ema3_prev * 100.0 if ema3_prev > 0 else 0.0
            ema3_above_ema9 = ema3_curr > ema9_curr

            if ema3_above_ema9:
                score += 10
            if ema3_slope > 0.1:
                score += 10
            elif ema3_slope < -0.3:
                score -= 10

            # Absorción en la última vela de 1H
            absorption_info = detect_candle_absorption(
                float(open_1h.iloc[-1]),
                float(high_1h.iloc[-1]),
                float(low_1h.iloc[-1]),
                float(close_1h.iloc[-1])
            )
            if absorption_info['has_absorption']:
                score += 10
        except Exception as e:
            log_warning(MODULE, f"Error evaluando indicadores 1H para Buying Force: {e}")

    final_score = int(max(0, min(100, score)))
    is_qualified = (final_score >= 70) and macro_aligned and (adr_pct >= 3.5)
    is_high_priority = (final_score >= 85) and is_qualified

    return {
        'score': final_score,
        'is_qualified': is_qualified,
        'is_high_priority': is_high_priority,
        'adr_pct': round(adr_pct, 2),
        'consumed_pct': round(consumed_pct, 1),
        'rvol_1h': round(rvol_1h, 2),
        'ema3_slope_1h': round(ema3_slope, 3),
        'ema3_above_ema9': ema3_above_ema9,
        'absorption': absorption_info,
        'macro_aligned': macro_aligned,
        'summary': (
            f"BuyingForce={final_score}/100 | Qualified={'SÍ' if is_qualified else 'NO'} | "
            f"Prioridad={'ALTA 🔥' if is_high_priority else 'NORMAL'} | "
            f"ADR={adr_pct:.2f}% | RVOL={rvol_1h:.2f}x"
        )
    }


def detect_pullback_and_climax_1h(
    current_price: float,
    df_1h: Optional[pd.DataFrame],
    macro_aligned: bool,
    df_15m: Optional[pd.DataFrame] = None
) -> dict:
    """
    Evalúa los Puntos de Entrada Duales en 1 HORA:
    - Ruta A: Pullback dinámico a EMA3, EMA9 o EMA20 en 1H con filtro anti-cuchillo de 15M.
    - Ruta B: Rebote Clímax en LOWER_5 o LOWER_6 en 1H.
    """
    if df_1h is None or len(df_1h) < 20 or current_price <= 0:
        return {
            'triggered': False,
            'route': None,
            'support_level': None,
            'reason': 'Datos 1H insuficientes'
        }

    try:
        close_1h = _safe_col(df_1h, 'close')
        open_1h = _safe_col(df_1h, 'open')
        high_1h = _safe_col(df_1h, 'high')
        low_1h = _safe_col(df_1h, 'low')

        ema3 = float(close_1h.ewm(span=3, adjust=False).mean().iloc[-1])
        ema9 = float(close_1h.ewm(span=9, adjust=False).mean().iloc[-1])
        ema20 = float(close_1h.ewm(span=20, adjust=False).mean().iloc[-1])

        # Sub-bandas Fibonacci de Bollinger en 1H
        bands_1h = calculate_fibonacci_bands(df_1h, current_price)
        lower_5 = float(bands_1h.get('lower_5', 0))
        lower_6 = float(bands_1h.get('lower_6', 0))
        basis = float(bands_1h.get('basis', ema20))

        last_low = float(low_1h.iloc[-1])
        last_high = float(high_1h.iloc[-1])
        last_open = float(open_1h.iloc[-1])
        last_close = float(close_1h.iloc[-1])

        absorption = detect_candle_absorption(last_open, last_high, last_low, last_close)

        # ── RUTA B: REBOTE CLÍMAX (LOWER_5 / LOWER_6 en 1H) ─────────────
        # Toque o perforación de bandas inferiores extremas en 1H con filtro obligatorio EMA3 > EMA9
        if lower_5 > 0 and ema3 > ema9:
            is_touch_lower_6 = (lower_6 > 0 and (last_low <= lower_6 or current_price <= lower_6 * 1.002))
            is_touch_lower_5 = (last_low <= lower_5 or current_price <= lower_5 * 1.002)

            if (is_touch_lower_6 or is_touch_lower_5) and macro_aligned:
                level_name = "LOWER_6" if is_touch_lower_6 else "LOWER_5"
                # Confirmación: absorción en la vela o cierre recuperando por encima del mínimo
                if absorption['has_absorption'] or current_price > last_low:
                    return {
                        'triggered': True,
                        'route': 'CLIMAX',
                        'support_level': level_name,
                        'price': current_price,
                        'level_price': lower_6 if is_touch_lower_6 else lower_5,
                        'ema3': ema3,
                        'ema9': ema9,
                        'ema20': ema20,
                        'absorption': absorption,
                        'reason': f'Rebote Clímax en 1H sobre {level_name} (${lower_5:.2f}) con Absorción ✅'
                    }

        # ── RUTA A: PULLBACK DINÁMICO (EMA3, EMA9, EMA20 en 1H) ──────────
        # Tolerancia de proximidad al soporte: hasta 0.40%
        supports = [
            ("EMA3", ema3, 0.0035),
            ("EMA9", ema9, 0.0040),
            ("EMA20", ema20, 0.0045)
        ]

        # Condición estricta de tendencia en 1H: Exige EMA3 > EMA9 sin excepción
        trend_1h_bullish = bool(ema3 > ema9)

        # Análisis de velas 15m para evitar "cuchillos cayendo"
        knife_falling_15m = False
        absorption_15m = False
        if df_15m is not None and len(df_15m) >= 2:
            try:
                c15_s = _safe_col(df_15m, 'close')
                o15_s = _safe_col(df_15m, 'open')
                h15_s = _safe_col(df_15m, 'high')
                l15_s = _safe_col(df_15m, 'low')

                c15_last = float(c15_s.iloc[-1])
                o15_last = float(o15_s.iloc[-1])
                h15_last = float(h15_s.iloc[-1])
                l15_last = float(l15_s.iloc[-1])

                rng_15 = max(1e-6, h15_last - l15_last)
                lower_wick_15 = max(0.0, min(o15_last, c15_last) - l15_last)
                lower_wick_15_pct = (lower_wick_15 / rng_15) * 100.0

                is_red_15 = c15_last < o15_last
                # Si la vela de 15m es roja sólida con mecha inferior < 25%, es un cuchillo cayendo
                knife_falling_15m = is_red_15 and (lower_wick_15_pct < 25.0)
                absorption_15m = (lower_wick_15_pct >= 28.0) or (c15_last >= o15_last)
            except Exception as e_15:
                log_warning(MODULE, f"Error analizando 15m en pullback 1H: {e_15}")

        for name, sup_price, tol in supports:
            if sup_price <= 0:
                continue

            dist = abs(current_price - sup_price) / sup_price
            touch_in_candle = (last_low <= sup_price <= last_high) or (dist <= tol)

            if touch_in_candle and trend_1h_bullish:
                # REGLA 1: Si es EMA3 pero en 15m las velas están en caída libre sin mecha,
                # NO comprar en EMA3. Esperar a que el retroceso llegue a EMA9.
                if name == "EMA3" and knife_falling_15m:
                    log_info(MODULE, f"Pullback EMA3 1H (${sup_price:.2f}) omitido: 15m en caída libre sin mecha. Esperando EMA9.")
                    continue

                # REGLA 2: Confirmación de rebote (Cierre verde o mecha de absorción en 1H o 15m)
                rebote_ok = (last_close >= sup_price * 0.998) and (
                    absorption['has_absorption'] or last_close >= last_open or absorption_15m
                )
                if rebote_ok:
                    wick_note = " + Absorción 15M" if absorption_15m else ""
                    return {
                        'triggered': True,
                        'route': 'PULLBACK',
                        'support_level': name,
                        'price': current_price,
                        'level_price': round(sup_price, 2),
                        'distance_pct': round(dist * 100, 2),
                        'ema3': ema3,
                        'ema9': ema9,
                        'ema20': ema20,
                        'absorption': absorption,
                        'reason': f'Pullback 1H a {name} (${sup_price:.2f}, dist={dist*100:.2f}%) con Rebote/Absorción{wick_note} ✅'
                    }

        return {
            'triggered': False,
            'route': None,
            'support_level': None,
            'reason': 'Sin pullback a soporte ni clímax en 1H'
        }

    except Exception as e:
        log_error(MODULE, f"Error evaluando entradas 1H: {e}")
        return {
            'triggered': False,
            'route': None,
            'support_level': None,
            'reason': f'Excepción: {e}'
        }
