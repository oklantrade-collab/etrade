"""
eTrade v6.0 — PULLBACK BUYING ENGINE FOR STOCKS
================================================
Motor cuantitativo de compras en retroceso para acciones en tendencia (Runners).

Estructura de Reglas:
1. CONDICIÓN MACRO (Cumple 'a' O 'b'):
   a. En 1H: EMA3 > EMA9  O  EMA3 ascendente (pendiente positiva).
   b. En 15M: Banda Superior Bollinger positiva (apuntando arriba) y
      Banda Inferior Bollinger negativa (apuntando abajo) con Precio >= Basis (SMA20).

2. FILTROS DE SEGURIDAD INTRADÍA:
   - Ventana Horaria: 10:00 ET a 14:15 ET (evita trampas de apertura y falta de tiempo al cierre).
   - Soporte VWAP: Precio actual >= VWAP * 0.995 (no comprar si el activo pierde el VWAP diario).

3. GATILLOS MICRO (5M / 15M):
   - Gatillo 1: Toque en LOWER_5 o LOWER_6 con vela de absorción (mecha inferior >= 30% o reversión verde).
   - Gatillo 2: Retesteo de EMA9 o EMA20 en 5m/15m con órdenes LIMIT + delta adaptativo y TTL de 5 minutos.

4. GESTIÓN ADUANA:
   - TP50 al tocar UPPER_5.
   - Stop Loss sube a Breakeven + 1.0% tras TP50.
   - Salida clímax en UPPER_6 o quiebre de EMA3 en 5m.
   - Hard Exit mandatario a las 15:50 ET.
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone, time as dt_time
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

from app.core.logger import log_info, log_warning, log_error

MODULE = "PULLBACK_ENGINE"


def _safe_col(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Extrae serie numérica insensible a mayúsculas."""
    if df is None:
        return pd.Series(dtype=float)
    if col_name in df.columns:
        return pd.to_numeric(df[col_name], errors='coerce')
    cap = col_name.capitalize()
    if cap in df.columns:
        return pd.to_numeric(df[cap], errors='coerce')
    upper = col_name.upper()
    if upper in df.columns:
        return pd.to_numeric(df[upper], errors='coerce')
    return pd.Series(dtype=float)


# ════════════════════════════════════════════════════════════════
# 1. EVALUADORES MACRO (1H y 15M)
# ════════════════════════════════════════════════════════════════

def evaluate_macro_1h_condition(df_1h: Optional[pd.DataFrame]) -> dict:
    """
    Condición (a):
    En 1 Hora: EMA3 > EMA9  O  EMA3 ascendente (ema3[-1] > ema3[-2]).
    """
    if df_1h is None or len(df_1h) < 10:
        return {
            'passed': False,
            'reason': 'Datos 1H insuficientes (<10 velas)',
            'ema3': 0.0,
            'ema9': 0.0,
            'ema3_rising': False,
            'ema3_gt_ema9': False
        }

    try:
        close_s = _safe_col(df_1h, 'close')
        ema3_s = close_s.ewm(span=3, adjust=False).mean()
        ema9_s = close_s.ewm(span=9, adjust=False).mean()

        ema3_curr = float(ema3_s.iloc[-1])
        ema3_prev = float(ema3_s.iloc[-2])
        ema9_curr = float(ema9_s.iloc[-1])

        ema3_gt_ema9 = ema3_curr > ema9_curr
        ema3_rising = ema3_curr > ema3_prev

        passed = ema3_gt_ema9 or ema3_rising
        reason = "EMA3 > EMA9" if ema3_gt_ema9 else ("EMA3 ascendente en 1H" if ema3_rising else "1H bajista")

        return {
            'passed': passed,
            'reason': reason,
            'ema3': round(ema3_curr, 3),
            'ema3_prev': round(ema3_prev, 3),
            'ema9': round(ema9_curr, 3),
            'ema3_rising': ema3_rising,
            'ema3_gt_ema9': ema3_gt_ema9
        }
    except Exception as e:
        log_warning(MODULE, f"Error evaluando macro 1H: {e}")
        return {
            'passed': False,
            'reason': f"Error: {e}",
            'ema3': 0.0,
            'ema9': 0.0,
            'ema3_rising': False,
            'ema3_gt_ema9': False
        }


def evaluate_macro_15m_bollinger_expansion(
    df_15m: Optional[pd.DataFrame],
    period: int = 20,
    mult: float = 2.0
) -> dict:
    """
    Condición (b):
    En 15 Minutos:
    - Banda Superior de Bollinger positiva (apuntando arriba: delta > 0).
    - Banda Inferior de Bollinger negativa (apuntando abajo: delta < 0).
    - MEJORA CRÍTICA: Precio >= Basis (SMA20) para garantizar que la expansión es alcista.
    """
    if df_15m is None or len(df_15m) < period + 2:
        return {
            'passed': False,
            'reason': 'Datos 15M insuficientes (<22 velas)',
            'upper_slope': 0.0,
            'lower_slope': 0.0,
            'basis': 0.0,
            'price_above_basis': False,
            'is_expanding': False
        }

    try:
        close_s = _safe_col(df_15m, 'close')
        sma = close_s.rolling(window=period).mean()
        std = close_s.rolling(window=period).std(ddof=0)

        upper = sma + (mult * std)
        lower = sma - (mult * std)
        basis = sma

        c_curr = float(close_s.iloc[-1])
        upper_curr = float(upper.iloc[-1])
        upper_prev = float(upper.iloc[-2])
        lower_curr = float(lower.iloc[-1])
        lower_prev = float(lower.iloc[-2])
        basis_curr = float(basis.iloc[-1])

        upper_slope = upper_curr - upper_prev
        lower_slope = lower_curr - lower_prev

        # Expansión: Upper sube y Lower baja
        is_expanding = (upper_slope > 0) and (lower_slope < 0)
        price_above_basis = c_curr >= basis_curr

        passed = is_expanding and price_above_basis
        if passed:
            reason = f"BB 15M Expansión Alcista (Upper +{upper_slope:.3f}, Lower {lower_slope:.3f}, P >= Basis)"
        elif is_expanding and not price_above_basis:
            reason = "BB 15M expandiendo pero precio bajo Basis (posible expansión bajista)"
        else:
            reason = "BB 15M sin expansión direccional"

        return {
            'passed': passed,
            'reason': reason,
            'upper_slope': round(upper_slope, 4),
            'lower_slope': round(lower_slope, 4),
            'basis': round(basis_curr, 3),
            'upper': round(upper_curr, 3),
            'lower': round(lower_curr, 3),
            'price_above_basis': price_above_basis,
            'is_expanding': is_expanding
        }
    except Exception as e:
        log_warning(MODULE, f"Error evaluando BB 15M: {e}")
        return {
            'passed': False,
            'reason': f"Error: {e}",
            'upper_slope': 0.0,
            'lower_slope': 0.0,
            'basis': 0.0,
            'price_above_basis': False,
            'is_expanding': False
        }


def evaluate_macro_pullback_gate(
    df_1h: Optional[pd.DataFrame],
    df_15m: Optional[pd.DataFrame]
) -> dict:
    """Evalúa la compuerta combinada Macro: Se cumple (a) 'O' (b)."""
    cond_a = evaluate_macro_1h_condition(df_1h)
    cond_b = evaluate_macro_15m_bollinger_expansion(df_15m)

    macro_passed = cond_a['passed'] or cond_b['passed']
    active_reasons = []
    if cond_a['passed']:
        active_reasons.append(f"1H: {cond_a['reason']}")
    if cond_b['passed']:
        active_reasons.append(f"15M: {cond_b['reason']}")

    return {
        'macro_passed': macro_passed,
        'cond_a': cond_a,
        'cond_b': cond_b,
        'summary_reason': " + ".join(active_reasons) if active_reasons else "Ninguna condición macro (1H ni 15M) activa"
    }


# ════════════════════════════════════════════════════════════════
# 2. FILTROS DE SEGURIDAD INTRADÍA
# ════════════════════════════════════════════════════════════════

def is_in_pullback_time_window(now_dt: Optional[datetime] = None) -> bool:
    """
    Retorna True si estamos en la ventana horaria óptima para compras en retroceso:
    10:00 ET a 14:15 ET.
    """
    if now_dt is None:
        try:
            now_dt = datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York'))
        except Exception:
            now_dt = datetime.now().astimezone(ZoneInfo('America/New_York'))
    elif getattr(now_dt, 'tzinfo', None) is not None:
        try:
            now_dt = now_dt.astimezone(ZoneInfo('America/New_York'))
        except Exception:
            pass

    t = now_dt.time()
    return dt_time(10, 0) <= t <= dt_time(14, 15)


def check_vwap_support(current_price: float, vwap: float) -> bool:
    """El precio no debe haber perdido el VWAP de la sesión."""
    if vwap <= 0 or current_price <= 0:
        return True
    return current_price >= (vwap * 0.995)


# ════════════════════════════════════════════════════════════════
# 3. GATILLOS MICRO DE ENTRADA (5M / 15M)
# ════════════════════════════════════════════════════════════════

def calculate_adaptive_limit_prices(
    current_price: float,
    ema9: float,
    ema20: float,
    spread: float = 0.02
) -> dict:
    """
    Calcula precios LIMIT adaptativos para EMA9 y EMA20:
    Delta = max(0.01, (spread * 0.5) + (price * 0.001))
    """
    delta = max(0.01, (spread * 0.5) + (current_price * 0.001))
    limit_ema9 = round(ema9 + delta, 2)
    limit_ema20 = round(ema20 + delta, 2)

    return {
        'limit_ema9': limit_ema9,
        'limit_ema20': limit_ema20,
        'delta': round(delta, 3)
    }


def evaluate_lower5_6_absorption(
    current_price: float,
    df_5m: Optional[pd.DataFrame],
    bands: Optional[dict] = None
) -> dict:
    """
    GATILLO 1:
    Precio ha llegado a LOWER_5 o LOWER_6 en 5m/15m y muestra absorción compradora
    (mecha inferior >= 30% del rango de la vela o vela verde de reversión).
    """
    if df_5m is None or len(df_5m) < 2 or not bands:
        return {'triggered': False, 'reason': 'Datos insuficientes para LOWER_5/6'}

    try:
        lower_5 = float(bands.get('lower_5', 0))
        lower_6 = float(bands.get('lower_6', 0))

        if lower_5 <= 0 and lower_6 <= 0:
            return {'triggered': False, 'reason': 'Bandas LOWER_5/6 no calculadas'}

        open_s = _safe_col(df_5m, 'open')
        high_s = _safe_col(df_5m, 'high')
        low_s = _safe_col(df_5m, 'low')
        close_s = _safe_col(df_5m, 'close')

        # Evaluar la vela actual y la previa
        recent_low = min(float(low_s.iloc[-1]), float(low_s.iloc[-2]))
        o = float(open_s.iloc[-1])
        h = float(high_s.iloc[-1])
        l = float(low_s.iloc[-1])
        c = float(close_s.iloc[-1])

        # ¿Tocó o rebasó LOWER_5 o LOWER_6?
        hit_lower6 = lower_6 > 0 and recent_low <= lower_6 * 1.006
        hit_lower5 = lower_5 > 0 and recent_low <= lower_5 * 1.004

        if not (hit_lower5 or hit_lower6):
            return {
                'triggered': False,
                'reason': f"Precio no ha alcanzado LOWER_5 (${lower_5:.2f}) ni LOWER_6 (${lower_6:.2f})"
            }

        level_name = "LOWER_6" if hit_lower6 else "LOWER_5"
        level_price = lower_6 if hit_lower6 else lower_5

        # Chequeo de absorción
        rng = max(1e-6, h - l)
        lower_wick = max(0.0, min(o, c) - l)
        lower_wick_pct = (lower_wick / rng) * 100.0
        is_green = c >= o

        has_wick = lower_wick_pct >= 28.0
        has_reversal = is_green and (c > float(close_s.iloc[-2]))

        if has_wick or has_reversal:
            return {
                'triggered': True,
                'level_name': level_name,
                'level_price': level_price,
                'lower_wick_pct': round(lower_wick_pct, 1),
                'is_green': is_green,
                'reason': f"Toque y absorción en {level_name} (${level_price:.2f}) con mecha {lower_wick_pct:.1f}% o cierre verde ✅"
            }

        return {
            'triggered': False,
            'reason': f"Tocó {level_name} pero sin absorción (vela aún en caída libre)"
        }
    except Exception as e:
        log_warning(MODULE, f"Error evaluando absorción en LOWER: {e}")
        return {'triggered': False, 'reason': f"Error: {e}"}


# ════════════════════════════════════════════════════════════════
# 4. EVALUADOR MAESTRO DE COMPRA EN RETROCESO (PULLBACK MASTER)
# ════════════════════════════════════════════════════════════════

def evaluate_pullback_setup(
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    bands_15m: Optional[dict] = None,
    vwap: float = 0.0,
    spread: float = 0.02,
    now_dt: Optional[datetime] = None
) -> dict:
    """
    EVALUADOR MAESTRO DE COMPRAS EN RETROCESO (PULLBACK BUYS)

    Coordina:
    1. Filtro Horario (10:00 a 14:15 ET).
    2. Filtro VWAP (Precio >= VWAP * 0.995).
    3. Confluencia Macro: Condición (a) 1H 'O' Condición (b) 15M BB Expansion.
    4. Gatillo Micro 1: Toque en LOWER_5/6 con absorción (Compra MARKET inmediata).
    5. Gatillo Micro 2: Retesteo de EMA9 o EMA20 (Órdenes LIMIT con Delta y TTL 5 min).
    """
    if current_price <= 0:
        return {
            'pullback_triggered': False,
            'trigger_type': None,
            'order_type': None,
            'reason': 'Precio inválido',
            'recommended_sl': 0.0,
            'target_upper5': 0.0,
            'target_upper6': 0.0,
            'limit_orders': []
        }

    # 1. Filtro Horario
    if not is_in_pullback_time_window(now_dt):
        return {
            'pullback_triggered': False,
            'trigger_type': None,
            'order_type': None,
            'reason': 'Fuera de ventana operativa de retroceso (10:00 ET a 14:15 ET)',
            'recommended_sl': 0.0,
            'target_upper5': 0.0,
            'target_upper6': 0.0,
            'limit_orders': []
        }

    # 2. Filtro VWAP
    if not check_vwap_support(current_price, vwap):
        return {
            'pullback_triggered': False,
            'trigger_type': None,
            'order_type': None,
            'reason': f"Precio (${current_price:.2f}) perforó VWAP de sesión (${vwap:.2f})",
            'recommended_sl': 0.0,
            'target_upper5': 0.0,
            'target_upper6': 0.0,
            'limit_orders': []
        }

    # 3. Macro Gate: 1H 'O' 15M BB Expansion
    macro_eval = evaluate_macro_pullback_gate(df_1h, df_15m)
    if not macro_eval['macro_passed']:
        return {
            'pullback_triggered': False,
            'trigger_type': None,
            'order_type': None,
            'reason': f"Macro no califica: {macro_eval['summary_reason']}",
            'recommended_sl': 0.0,
            'target_upper5': 0.0,
            'target_upper6': 0.0,
            'limit_orders': []
        }

    # 4. Objetivos y Niveles Aduana
    target_u5 = float(bands_15m.get('upper_5', current_price * 1.05)) if bands_15m else current_price * 1.05
    target_u6 = float(bands_15m.get('upper_6', current_price * 1.08)) if bands_15m else current_price * 1.08
    
    # Calcular EMAs en 5m
    ema9_5m = current_price
    ema20_5m = current_price
    last_low = current_price * 0.985
    if df_5m is not None and len(df_5m) >= 20:
        c_5m = _safe_col(df_5m, 'close')
        l_5m = _safe_col(df_5m, 'low')
        ema9_5m = float(c_5m.ewm(span=9, adjust=False).mean().iloc[-1])
        ema20_5m = float(c_5m.ewm(span=20, adjust=False).mean().iloc[-1])
        last_low = float(l_5m.iloc[-3:].min())

    rec_sl = round(max(current_price * 0.975, last_low * 0.995), 2)

    # ════════════════════════════════════════════════════════════════
    # GATILLO 1: Toque y Absorción en LOWER_5 o LOWER_6 (Market/Inmediata)
    # ════════════════════════════════════════════════════════════════
    lower_absorb = evaluate_lower5_6_absorption(current_price, df_5m, bands_15m)
    if lower_absorb['triggered']:
        return {
            'pullback_triggered': True,
            'trigger_type': 'PULLBACK_LOWER_ABSORPTION',
            'order_type': 'market',
            'reason': f"{lower_absorb['reason']} [Macro: {macro_eval['summary_reason']}]",
            'recommended_sl': rec_sl,
            'target_upper5': round(target_u5, 2),
            'target_upper6': round(target_u6, 2),
            'macro_details': macro_eval,
            'limit_orders': []
        }

    # ════════════════════════════════════════════════════════════════
    # GATILLO 2: Órdenes LIMIT en EMA9 y EMA20 con Delta Adaptativo
    # ════════════════════════════════════════════════════════════════
    # Si el precio está cerca (a <= 2.0%) de EMA9 o EMA20
    dist_ema9 = abs(current_price - ema9_5m) / max(1e-6, ema9_5m)
    dist_ema20 = abs(current_price - ema20_5m) / max(1e-6, ema20_5m)

    if dist_ema9 <= 0.020 or dist_ema20 <= 0.020:
        limits = calculate_adaptive_limit_prices(current_price, ema9_5m, ema20_5m, spread)
        limit_orders_payload = [
            {
                'ema_target': 'EMA9',
                'target_price': round(ema9_5m, 2),
                'limit_price': limits['limit_ema9'],
                'ttl_minutes': 5,
                'delta': limits['delta']
            },
            {
                'ema_target': 'EMA20',
                'target_price': round(ema20_5m, 2),
                'limit_price': limits['limit_ema20'],
                'ttl_minutes': 5,
                'delta': limits['delta']
            }
        ]

        return {
            'pullback_triggered': True,
            'trigger_type': 'PULLBACK_EMA_LIMIT',
            'order_type': 'limit',
            'reason': f"Retesteo EMA9 (${ema9_5m:.2f}) / EMA20 (${ema20_5m:.2f}) con Órdenes LIMIT y TTL 5m [Macro: {macro_eval['summary_reason']}]",
            'recommended_sl': rec_sl,
            'target_upper5': round(target_u5, 2),
            'target_upper6': round(target_u6, 2),
            'macro_details': macro_eval,
            'limit_orders': limit_orders_payload
        }

    return {
        'pullback_triggered': False,
        'trigger_type': None,
        'order_type': None,
        'reason': f"En espera de retroceso a LOWER_5/6 o EMA9/20 (${current_price:.2f} vs EMA9=${ema9_5m:.2f})",
        'recommended_sl': rec_sl,
        'target_upper5': round(target_u5, 2),
        'target_upper6': round(target_u6, 2),
        'macro_details': macro_eval,
        'limit_orders': []
    }
