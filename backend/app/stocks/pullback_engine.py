"""
eTrade v6.0 — PULLBACK & STRUCTURAL BUY ENGINE FOR STOCKS (SECCIÓN B)
=====================================================================
Motor cuantitativo de compras y recompras estructurales para acciones en tendencia y Alpha Runners.

Estructura de Reglas (Sección B):
1. CONDICIONES BÁSICAS EN 1 HORA (Cumple 'a' O 'b'):
   a. En temporalidad de 1 hora: EMA3 > EMA9
   b. En temporalidad de 1 hora: Banda Superior Bollinger ascendente (slope > 0) y
      Banda Inferior Bollinger descendente (slope < 0).

2. REGLA 3a — RETROCESO A EMA3 DE 1 HORA:
   - En 1 hora: Precio OPEN <= EMA3_1H (o Low_1H toca EMA3_1H).
   - En 5m / 15m cumple cualquiera de:
       * CLOSE < BANDA_INFERIOR_BOLLINGER
       * LOW < LOWER_5
       * LOW < LOWER_6
   - Confirmación Anti-Cuchillo: Mecha inferior >= 20% o vela verde / recupero de EMA3_5m.

3. REGLA 4 — REBOTE EN EMA9 O EMA20 DE 1 HORA (Cumple cualquiera de 4a, 4b, 4c, 4d):
   - 4a: En 5m/15m señal PINESCRIPT "BUY" con precio < UPPER_3.
   - 4b: Pasa de EMA3 < EMA9 a EMA3 > EMA9 en 5m o 15m (precio < UPPER_3).
   - 4c: El precio toca la (Banda Inferior Bollinger - Delta) en 5m con absorción.
   - 4d: Según SIPV aparece una vela de cambio de tendencia cuando el precio está
         en cualquiera de las bandas Fibonacci BASIS, UPPER_1, UPPER_2, UPPER_3 en 15m.

4. REGLA 5 — DOBLE CONTROL Y TRAILING STOP ESCALONADO (Pasadas 3 velas de 5m):
   - Etapa 1: OPEN de la vela de 5m superior al precio de compra.
   - Etapa 2: (EMA9_15m - Delta) en 15m.
   - Etapa 3: (EMA3_15m - Delta) cuando ((OPEN > BB_Upper) y (CLOSE > OPEN)).
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
# 1. EVALUADORES MACRO (CONDICIONES BÁSICAS 1H a/b Y 15M)
# ════════════════════════════════════════════════════════════════

def evaluate_macro_1h_condition(df_1h: Optional[pd.DataFrame]) -> dict:
    """
    Condiciones Básicas en 1 Hora (Sección B):
      a. En temporalidad de 1 hora, EMA3 > EMA9
      b. Banda superior Bollinger ascendente y Banda inferior Bollinger descendente, en temporalidad de 1 hora
    """
    if df_1h is None or len(df_1h) < 6:
        return {
            'passed': False,
            'reason': 'Datos 1H insuficientes (<6 velas)',
            'ema3': 0.0,
            'ema9': 0.0,
            'ema20': 0.0,
            'open_1h': 0.0,
            'low_1h': 0.0,
            'cond_a_ema3_gt_ema9': False,
            'cond_b_bb_1h_expanding': False,
            'ema3_rising': False,
            'ema3_gt_ema9': False
        }

    try:
        close_s = _safe_col(df_1h, 'close')
        open_s = _safe_col(df_1h, 'open')
        low_s = _safe_col(df_1h, 'low')

        ema3_s = close_s.ewm(span=3, adjust=False).mean()
        ema9_s = close_s.ewm(span=9, adjust=False).mean()
        ema20_s = close_s.ewm(span=20, adjust=False).mean()

        ema3_curr = float(ema3_s.iloc[-1])
        ema3_prev = float(ema3_s.iloc[-2]) if len(ema3_s) >= 2 else ema3_curr
        ema9_curr = float(ema9_s.iloc[-1])
        ema9_prev = float(ema9_s.iloc[-2]) if len(ema9_s) >= 2 else ema9_curr
        ema20_curr = float(ema20_s.iloc[-1])
        open_1h_curr = float(open_s.iloc[-1])
        low_1h_curr = float(low_s.iloc[-1])

        # Condición (a): EMA3 > EMA9 en 1H
        cond_a = ema3_curr > ema9_curr
        ema3_rising = ema3_curr > ema3_prev
        ema9_rising = ema9_curr >= ema9_prev * 0.998

        # Condición (b): BB Superior 1H ascendente y BB Inferior 1H descendente
        cond_b = False
        bb_up_slope_1h = 0.0
        bb_lo_slope_1h = 0.0
        if len(close_s) >= 12:
            win = min(20, len(close_s) - 1)
            sma1h = close_s.rolling(window=win, min_periods=5).mean()
            std1h = close_s.rolling(window=win, min_periods=5).std(ddof=0).fillna(0)
            up1h = sma1h + 2.0 * std1h
            lo1h = sma1h - 2.0 * std1h
            bb_up_slope_1h = float(up1h.iloc[-1] - up1h.iloc[-2])
            bb_lo_slope_1h = float(lo1h.iloc[-1] - lo1h.iloc[-2])
            cond_b = (bb_up_slope_1h > 0) and (bb_lo_slope_1h < 0)

        passed = cond_a or cond_b or ema3_rising
        reasons = []
        if cond_a:
            reasons.append(f"1H(a): EMA3({ema3_curr:.2f})>EMA9({ema9_curr:.2f})")
        if cond_b:
            reasons.append(f"1H(b): BB_Up↑({bb_up_slope_1h:+.3f}) & BB_Lo↓({bb_lo_slope_1h:+.3f})")
        if not reasons and ema3_rising:
            reasons.append("1H: EMA3 ascendente")

        return {
            'passed': passed,
            'reason': " | ".join(reasons) if reasons else "1H sin tendencia alcista",
            'ema3': round(ema3_curr, 4),
            'ema3_prev': round(ema3_prev, 4),
            'ema9': round(ema9_curr, 4),
            'ema9_rising': ema9_rising,
            'ema20': round(ema20_curr, 4),
            'open_1h': round(open_1h_curr, 4),
            'low_1h': round(low_1h_curr, 4),
            'cond_a_ema3_gt_ema9': cond_a,
            'cond_b_bb_1h_expanding': cond_b,
            'ema3_rising': ema3_rising,
            'ema3_gt_ema9': cond_a
        }
    except Exception as e:
        log_warning(MODULE, f"Error evaluando macro 1H: {e}")
        return {
            'passed': False,
            'reason': f"Error: {e}",
            'ema3': 0.0,
            'ema9': 0.0,
            'ema20': 0.0,
            'open_1h': 0.0,
            'low_1h': 0.0,
            'cond_a_ema3_gt_ema9': False,
            'cond_b_bb_1h_expanding': False,
            'ema3_rising': False,
            'ema3_gt_ema9': False
        }


def evaluate_macro_15m_bollinger_expansion(
    df_15m: Optional[pd.DataFrame],
    period: int = 20,
    mult: float = 2.0
) -> dict:
    """
    Condición auxiliar en 15 Minutos:
    - Banda Superior de Bollinger positiva (delta > 0) y Banda Inferior negativa (delta < 0).
    """
    if df_15m is None or len(df_15m) < 12:
        return {
            'passed': False,
            'reason': 'Datos 15M insuficientes',
            'upper_slope': 0.0,
            'lower_slope': 0.0,
            'basis': 0.0,
            'price_above_basis': False,
            'is_expanding': False
        }

    try:
        close_s = _safe_col(df_15m, 'close')
        win = min(period, len(close_s) - 1)
        sma = close_s.rolling(window=win, min_periods=5).mean()
        std = close_s.rolling(window=win, min_periods=5).std(ddof=0).fillna(0)

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

        is_expanding = (upper_slope > 0) and (lower_slope < 0)
        price_above_basis = c_curr >= basis_curr

        passed = is_expanding and price_above_basis
        reason = (
            f"BB 15M Expansión Alcista (Upper +{upper_slope:.3f}, Lower {lower_slope:.3f})"
            if passed else "BB 15M sin expansión alcista"
        )

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
    """Evalúa la compuerta combinada Macro: Se cumple 1H (a o b) O 15M BB Expansion."""
    cond_a = evaluate_macro_1h_condition(df_1h)
    cond_b = evaluate_macro_15m_bollinger_expansion(df_15m)

    macro_passed = cond_a['passed'] or cond_b['passed']
    active_reasons = []
    if cond_a['passed']:
        active_reasons.append(cond_a['reason'])
    if cond_b['passed']:
        active_reasons.append(cond_b['reason'])

    return {
        'macro_passed': macro_passed,
        'cond_a': cond_a,
        'cond_b': cond_b,
        'summary_reason': " + ".join(active_reasons) if active_reasons else "Ninguna condición básica 1H (a/b) activa"
    }


# ════════════════════════════════════════════════════════════════
# 2. FILTROS DE SEGURIDAD INTRADÍA
# ════════════════════════════════════════════════════════════════

def is_in_pullback_time_window(now_dt: Optional[datetime] = None) -> bool:
    """
    Ventana operativa para compras y recompras intradía:
    09:40 ET a 15:10 ET (respeta el cutoff EOD de las 15:15 ET).
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
    return dt_time(9, 40) <= t <= dt_time(15, 10)


def check_vwap_support(current_price: float, vwap: float) -> bool:
    """El precio no debe estar colapsando profundamente bajo el VWAP."""
    if vwap <= 0 or current_price <= 0:
        return True
    return current_price >= (vwap * 0.985)


# ════════════════════════════════════════════════════════════════
# 3. GATILLOS DE COMPRA / RECOMPRA SECCIÓN B (3a, 4a, 4b, 4c, 4d)
# ════════════════════════════════════════════════════════════════

def calculate_adaptive_limit_prices(
    current_price: float,
    ema9: float,
    ema20: float,
    spread: float = 0.02
) -> dict:
    delta = max(0.01, (spread * 0.5) + (current_price * 0.001))
    return {
        'limit_ema9': round(ema9 + delta, 2),
        'limit_ema20': round(ema20 + delta, 2),
        'delta': round(delta, 3)
    }


def evaluate_rule_3a_ema3_1h_dip(
    current_price: float,
    cond_1h: dict,
    df_5m: Optional[pd.DataFrame],
    df_15m: Optional[pd.DataFrame],
    bands_15m: Optional[dict] = None
) -> dict:
    """
    REGLA 3a (SECCIÓN B.3):
    - En temporalidad de 1 hora: Precio OPEN <= EMA3_1H (o Low_1H toca EMA3_1H en retroceso sano).
    - Buscamos en temporalidad de 5m o 15m cualquiera de:
        1) CLOSE < BANDA_INFERIOR_BOLLINGER
        2) LOW < LOWER_5
        3) LOW < LOWER_6
    - Filtro Anti-Cuchillo: Mecha inferior >= 20% o vela verde / precio recuperando EMA3_5m.
    """
    if df_5m is None or len(df_5m) < 6:
        return {'triggered': False, 'reason': 'Datos 5m insuficientes para 3a'}

    try:
        ema3_1h = float(cond_1h.get('ema3') or 0.0)
        open_1h = float(cond_1h.get('open_1h') or 0.0)
        low_1h = float(cond_1h.get('low_1h') or 0.0)

        # Condición 3 en 1H: Open_1H <= EMA3_1H (o Low_1H <= EMA3_1H * 1.005)
        cond_3_1h = (ema3_1h > 0) and ((open_1h <= ema3_1h * 1.003) or (low_1h <= ema3_1h * 1.005) or (current_price <= ema3_1h * 1.005))
        if not cond_3_1h:
            return {'triggered': False, 'reason': f"1H Open (${open_1h:.2f}) / Precio (${current_price:.2f}) > EMA3_1H (${ema3_1h:.2f})"}

        # Evaluar en 5m y 15m: Close < BB_Lower, Low < LOWER_5, Low < LOWER_6
        c5 = _safe_col(df_5m, 'close')
        o5 = _safe_col(df_5m, 'open')
        h5 = _safe_col(df_5m, 'high')
        l5 = _safe_col(df_5m, 'low')

        win5 = min(20, len(c5) - 1)
        sma5 = c5.rolling(win5, min_periods=5).mean()
        std5 = c5.rolling(win5, min_periods=5).std(ddof=0).fillna(0)
        bb_lo_5 = sma5 - 2.0 * std5
        ema3_5 = float(c5.ewm(span=3, adjust=False).mean().iloc[-1])

        # Bandas Fibonacci en 5m y 15m
        from app.strategy.panic_recovery_gate import calculate_fibonacci_bands
        fib_5m = calculate_fibonacci_bands(df_5m, current_price)
        lower5_5m = float(fib_5m.get('lower_5') or 0.0)
        lower6_5m = float(fib_5m.get('lower_6') or 0.0)

        lower5_15m = float((bands_15m or {}).get('lower_5') or 0.0)
        lower6_15m = float((bands_15m or {}).get('lower_6') or 0.0)

        # Revisar las últimas 2 velas de 5m
        recent_low_5m = min(float(l5.iloc[-1]), float(l5.iloc[-2]))
        recent_close_5m = min(float(c5.iloc[-1]), float(c5.iloc[-2]))
        bb_lo_5_val = float(bb_lo_5.iloc[-1])

        close_lt_bb_lower = (bb_lo_5_val > 0 and recent_close_5m < bb_lo_5_val * 1.002)
        if not close_lt_bb_lower and df_15m is not None and len(df_15m) >= 6:
            c15 = _safe_col(df_15m, 'close')
            win15 = min(20, len(c15) - 1)
            bb_lo_15 = float((c15.rolling(win15, min_periods=5).mean() - 2.0 * c15.rolling(win15, min_periods=5).std(ddof=0).fillna(0)).iloc[-1])
            if bb_lo_15 > 0 and float(c15.iloc[-1]) < bb_lo_15 * 1.002:
                close_lt_bb_lower = True

        low_lt_lower5 = (lower5_5m > 0 and recent_low_5m <= lower5_5m * 1.003) or (lower5_15m > 0 and recent_low_5m <= lower5_15m * 1.003)
        low_lt_lower6 = (lower6_5m > 0 and recent_low_5m <= lower6_5m * 1.004) or (lower6_15m > 0 and recent_low_5m <= lower6_15m * 1.004)

        if not (close_lt_bb_lower or low_lt_lower5 or low_lt_lower6):
            return {'triggered': False, 'reason': 'Sin extremo en 5m/15m (Close < BB_Lower o Low < LOWER_5/6)'}

        # Confirmación de absorción (mecha inferior >= 20% o vela verde o recupero de EMA3_5m)
        o_cur, h_cur, l_cur, c_cur = float(o5.iloc[-1]), float(h5.iloc[-1]), float(l5.iloc[-1]), float(c5.iloc[-1])
        rng_cur = max(1e-6, h_cur - l_cur)
        lower_wick_pct = (max(0.0, min(o_cur, c_cur) - l_cur) / rng_cur) * 100.0
        is_absorbing = (lower_wick_pct >= 20.0) or (c_cur >= o_cur) or (current_price >= ema3_5)

        if not is_absorbing:
            return {'triggered': False, 'reason': 'Tocó banda inferior pero aún sin mecha de rechazo >= 20% ni vela verde'}

        sub_tag = "LOW<LOWER_6" if low_lt_lower6 else ("LOW<LOWER_5" if low_lt_lower5 else "CLOSE<BB_LOWER")
        return {
            'triggered': True,
            'rule_code': 'PULLBACK_3A_EMA3_1H_DIP',
            'reason': f"Regla 3a Activa: 1H Open/Low <= EMA3_1H (${ema3_1h:.2f}) + {sub_tag} con absorción ({lower_wick_pct:.1f}% mecha)"
        }
    except Exception as e:
        log_warning(MODULE, f"Error en Regla 3a: {e}")
        return {'triggered': False, 'reason': str(e)}


def evaluate_rule_4_ema9_20_1h_bounce(
    current_price: float,
    cond_1h: dict,
    df_5m: Optional[pd.DataFrame],
    df_15m: Optional[pd.DataFrame],
    bands_15m: Optional[dict] = None,
    pinescript_signal: str = '',
    sipv_signal_15m: str = '',
    spread: float = 0.02
) -> dict:
    """
    REGLA 4 (SECCIÓN B.4) — REBOTE EN EMA9 O EMA20 DE 1 HORA:
    Cuando el precio rebota/se apoya en la zona de EMA9_1H o EMA20_1H y cumple CUALQUIERA de:
      - 4a: En 5m/15m señal PINESCRIPT "BUY" con precio < UPPER_3.
      - 4b: Pasa de EMA3 < EMA9 a EMA3 > EMA9 en 5m o 15m (con precio < UPPER_3).
      - 4c: El precio toca (Banda Inferior Bollinger - Delta) en 5m.
      - 4d: Según SIPV aparece una vela de cambio de tendencia alcista cuando el precio está
            en cualquiera de las bandas Fibonacci BASIS, UPPER_1, UPPER_2, UPPER_3 en 15m.
    """
    if df_5m is None or len(df_5m) < 6 or df_15m is None or len(df_15m) < 6:
        return {'triggered': False, 'reason': 'Datos 5m/15m insuficientes para Regla 4'}

    try:
        ema9_1h = float(cond_1h.get('ema9') or 0.0)
        ema20_1h = float(cond_1h.get('ema20') or 0.0)
        low_1h = float(cond_1h.get('low_1h') or current_price)

        # Verificar proximidad/rebote sobre EMA9_1H o EMA20_1H (o soporte dinámico cuando 1H es alcista)
        near_ema9_1h = (ema9_1h > 0) and (low_1h <= ema9_1h * 1.025 or abs(current_price - ema9_1h) / ema9_1h <= 0.025) and (current_price >= ema9_1h * 0.985)
        near_ema20_1h = (ema20_1h > 0) and (low_1h <= ema20_1h * 1.025 or abs(current_price - ema20_1h) / ema20_1h <= 0.025) and (current_price >= ema20_1h * 0.985)
        in_1h_support_zone = near_ema9_1h or near_ema20_1h or (cond_1h.get('passed', False) and ema20_1h > 0 and current_price >= ema20_1h * 0.99)

        if not in_1h_support_zone:
            return {'triggered': False, 'reason': f"Precio (${current_price:.2f}) fuera de zona de rebote EMA9_1H (${ema9_1h:.2f}) / EMA20_1H (${ema20_1h:.2f})"}

        support_label = "EMA9_1H" if near_ema9_1h else ("EMA20_1H" if near_ema20_1h else "1H_BULL_ZONE")

        # Bandas Fibonacci en 15m
        from app.strategy.panic_recovery_gate import calculate_fibonacci_bands
        fib_15 = bands_15m if (bands_15m and bands_15m.get('upper_3')) else calculate_fibonacci_bands(df_15m, current_price)
        basis_15 = float(fib_15.get('basis') or current_price * 0.98)
        upper3_15 = float(fib_15.get('upper_3') or current_price * 1.05)

        below_upper3 = (upper3_15 <= 0) or (current_price < upper3_15)

        # Series de 5m y 15m
        c5 = _safe_col(df_5m, 'close')
        o5 = _safe_col(df_5m, 'open')
        h5 = _safe_col(df_5m, 'high')
        l5 = _safe_col(df_5m, 'low')

        c15 = _safe_col(df_15m, 'close')
        o15 = _safe_col(df_15m, 'open')
        h15 = _safe_col(df_15m, 'high')
        l15 = _safe_col(df_15m, 'low')

        # ── SUB-REGLA 4a: Señal PINESCRIPT "BUY" en 5m/15m y Precio < UPPER_3 ──
        pine_buy = str(pinescript_signal or '').upper() == 'BUY'
        if not pine_buy:
            ema3_15_s = c15.ewm(span=3, adjust=False).mean()
            ema9_15_s = c15.ewm(span=9, adjust=False).mean()
            if float(ema3_15_s.iloc[-1]) > float(ema9_15_s.iloc[-1]) and float(c15.iloc[-1]) > float(o15.iloc[-1]) and (near_ema9_1h or near_ema20_1h):
                pine_buy = True

        if pine_buy and below_upper3 and (near_ema9_1h or near_ema20_1h):
            return {
                'triggered': True,
                'rule_code': 'PULLBACK_4A_EMA1H_PINE_BUY',
                'reason': f"Regla 4a Activa: Rebote en {support_label} + Señal PineScript BUY con Precio (${current_price:.2f}) < UPPER_3 (${upper3_15:.2f})"
            }

        # ── SUB-REGLA 4b: Pasa de EMA3 < EMA9 a EMA3 > EMA9 en 5m o 15m ──
        ema3_5 = c5.ewm(span=3, adjust=False).mean()
        ema9_5 = c5.ewm(span=9, adjust=False).mean()
        cross_5m = (float(ema3_5.iloc[-1]) > float(ema9_5.iloc[-1])) and (
            float(ema3_5.iloc[-2]) <= float(ema9_5.iloc[-2]) or (len(ema3_5) >= 3 and float(ema3_5.iloc[-3]) <= float(ema9_5.iloc[-3]))
        )

        ema3_15 = c15.ewm(span=3, adjust=False).mean()
        ema9_15 = c15.ewm(span=9, adjust=False).mean()
        cross_15m = (float(ema3_15.iloc[-1]) > float(ema9_15.iloc[-1])) and (
            float(ema3_15.iloc[-2]) <= float(ema9_15.iloc[-2]) or (len(ema3_15) >= 3 and float(ema3_15.iloc[-3]) <= float(ema9_15.iloc[-3]))
        )

        if (cross_5m or cross_15m) and below_upper3:
            tf_str = "5m" if cross_5m else "15m"
            return {
                'triggered': True,
                'rule_code': 'PULLBACK_4B_EMA1H_CROSS_3_9',
                'reason': f"Regla 4b Activa: Rebote en {support_label} + Cruce fresco EMA3 > EMA9 en {tf_str} (< UPPER_3 ${upper3_15:.2f})"
            }

        # ── SUB-REGLA 4c: Precio toca (Banda Inferior Bollinger - Delta) en 5m ──
        win5 = min(20, len(c5) - 1)
        sma5 = c5.rolling(win5, min_periods=5).mean()
        std5 = c5.rolling(win5, min_periods=5).std(ddof=0).fillna(0)
        bb_lo_5 = float((sma5 - 2.0 * std5).iloc[-1])
        delta_5 = max(0.01, (spread * 0.5) + (current_price * 0.001))
        recent_low_5m = min(float(l5.iloc[-1]), float(l5.iloc[-2]))
        if bb_lo_5 > 0 and recent_low_5m <= (bb_lo_5 - delta_5) * 1.003 and float(c5.iloc[-1]) >= float(o5.iloc[-1]):
            return {
                'triggered': True,
                'rule_code': 'PULLBACK_4C_EMA1H_BB5M_LOWER',
                'reason': f"Regla 4c Activa: Rebote en {support_label} + Toque en (BB_Lower_5m ${bb_lo_5:.2f} - Δ ${delta_5:.2f}) con giro verde"
            }

        # ── SUB-REGLA 4d: Vela SIPV de cambio de tendencia en BASIS, UPPER_1, UPPER_2 o UPPER_3 de 15m ──
        in_fib_basis_to_u3 = (basis_15 * 0.995 <= current_price <= upper3_15 * 1.002)
        if in_fib_basis_to_u3:
            o15_cur, h15_cur, l15_cur, c15_cur = float(o15.iloc[-1]), float(h15.iloc[-1]), float(l15.iloc[-1]), float(c15.iloc[-1])
            o15_prev, c15_prev = float(o15.iloc[-2]), float(c15.iloc[-2])
            rng15 = max(1e-6, h15_cur - l15_cur)
            lower_wick_15 = max(0.0, min(o15_cur, c15_cur) - l15_cur) / rng15
            body_15 = (c15_cur - o15_cur) / rng15

            is_sipv_reversal = (
                str(sipv_signal_15m or '').upper() == 'BUY'
                or (c15_cur > o15_cur and lower_wick_15 >= 0.35)
                or (c15_prev < o15_prev and c15_cur > o15_cur and body_15 >= 0.35 and c15_cur > o15_prev)
            )
            if is_sipv_reversal:
                return {
                    'triggered': True,
                    'rule_code': 'PULLBACK_4D_EMA1H_SIPV_FIB',
                    'reason': f"Regla 4d Activa: Rebote en {support_label} + Vela SIPV de cambio de tendencia en banda Fibonacci [Basis ${basis_15:.2f} - Upper_3 ${upper3_15:.2f}]"
                }

        return {'triggered': False, 'reason': 'En zona 1H pero esperando gatillo 4a/4b/4c/4d en 5m/15m'}
    except Exception as e:
        log_warning(MODULE, f"Error en Regla 4 (4a-4d): {e}")
        return {'triggered': False, 'reason': str(e)}


def evaluate_lower5_6_absorption(
    current_price: float,
    df_5m: Optional[pd.DataFrame],
    bands: Optional[dict] = None
) -> dict:
    """
    GATILLO ADICIONAL:
    Precio ha llegado a LOWER_5 o LOWER_6 en 5m/15m y muestra absorción compradora.
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

        recent_low = min(float(low_s.iloc[-1]), float(low_s.iloc[-2]))
        o = float(open_s.iloc[-1])
        h = float(high_s.iloc[-1])
        l = float(low_s.iloc[-1])
        c = float(close_s.iloc[-1])

        hit_lower6 = lower_6 > 0 and recent_low <= lower_6 * 1.006
        hit_lower5 = lower_5 > 0 and recent_low <= lower_5 * 1.004

        if not (hit_lower5 or hit_lower6):
            return {
                'triggered': False,
                'reason': f"Precio no ha alcanzado LOWER_5 (${lower_5:.2f}) ni LOWER_6 (${lower_6:.2f})"
            }

        level_name = "LOWER_6" if hit_lower6 else "LOWER_5"
        level_price = lower_6 if hit_lower6 else lower_5

        rng = max(1e-6, h - l)
        lower_wick = max(0.0, min(o, c) - l)
        lower_wick_pct = (lower_wick / rng) * 100.0
        is_green = c >= o

        has_wick = lower_wick_pct >= 25.0
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
# 4. EVALUADOR MAESTRO DE COMPRA EN RETROCESO (SECCIÓN B MASTER)
# ════════════════════════════════════════════════════════════════

def evaluate_pullback_setup(
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    bands_15m: Optional[dict] = None,
    vwap: float = 0.0,
    spread: float = 0.02,
    now_dt: Optional[datetime] = None,
    pinescript_signal: str = '',
    sipv_signal_15m: str = '',
) -> dict:
    """
    EVALUADOR MAESTRO DE COMPRAS Y RECOMPRAS (SECCIÓN B: 3a, 4a, 4b, 4c, 4d)
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

    # 1. Filtro Horario (09:40 a 15:10 ET)
    if not is_in_pullback_time_window(now_dt):
        return {
            'pullback_triggered': False,
            'trigger_type': None,
            'order_type': None,
            'reason': 'Fuera de ventana operativa intradía (09:40 ET a 15:10 ET)',
            'recommended_sl': 0.0,
            'target_upper5': 0.0,
            'target_upper6': 0.0,
            'limit_orders': []
        }

    # 2. Macro Gate: Condición Básica 1H (a: EMA3>EMA9, b: BB_1H expandiendo) o 15M BB Expansion
    macro_eval = evaluate_macro_pullback_gate(df_1h, df_15m)
    if not macro_eval['macro_passed']:
        return {
            'pullback_triggered': False,
            'trigger_type': None,
            'order_type': None,
            'reason': f"Condición básica 1H no activa: {macro_eval['summary_reason']}",
            'recommended_sl': 0.0,
            'target_upper5': 0.0,
            'target_upper6': 0.0,
            'limit_orders': []
        }

    # 3. Objetivos y Stop Loss Inicial Doble Control
    target_u5 = float(bands_15m.get('upper_5', current_price * 1.05)) if bands_15m else current_price * 1.05
    target_u6 = float(bands_15m.get('upper_6', current_price * 1.08)) if bands_15m else current_price * 1.08

    ema9_5m = current_price
    ema20_5m = current_price
    last_low = current_price * 0.98
    if df_5m is not None and len(df_5m) >= 10:
        c_5m = _safe_col(df_5m, 'close')
        l_5m = _safe_col(df_5m, 'low')
        ema9_5m = float(c_5m.ewm(span=9, adjust=False).mean().iloc[-1])
        ema20_5m = float(c_5m.ewm(span=20, adjust=False).mean().iloc[-1])
        last_low = float(l_5m.iloc[-3:].min())

    rec_sl = round(max(current_price * 0.965, min(current_price * 0.988, last_low * 0.994)), 2)
    cond_1h = macro_eval.get('cond_a', {})

    # ════════════════════════════════════════════════════════════════
    # REGLA 3a: Open_1H <= EMA3_1H + (Close < BB_Lower o Low < LOWER_5/6 en 5m/15m)
    # ════════════════════════════════════════════════════════════════
    res_3a = evaluate_rule_3a_ema3_1h_dip(current_price, cond_1h, df_5m, df_15m, bands_15m)
    if res_3a.get('triggered'):
        return {
            'pullback_triggered': True,
            'trigger_type': res_3a['rule_code'],
            'order_type': 'market',
            'reason': f"{res_3a['reason']} [Macro: {macro_eval['summary_reason']}]",
            'recommended_sl': rec_sl,
            'target_upper5': round(target_u5, 2),
            'target_upper6': round(target_u6, 2),
            'macro_details': macro_eval,
            'limit_orders': []
        }

    # ════════════════════════════════════════════════════════════════
    # REGLA 4 (4a, 4b, 4c, 4d): Rebote en EMA9 o EMA20 de 1 Hora
    # ════════════════════════════════════════════════════════════════
    res_4 = evaluate_rule_4_ema9_20_1h_bounce(
        current_price=current_price,
        cond_1h=cond_1h,
        df_5m=df_5m,
        df_15m=df_15m,
        bands_15m=bands_15m,
        pinescript_signal=pinescript_signal,
        sipv_signal_15m=sipv_signal_15m,
        spread=spread
    )
    if res_4.get('triggered'):
        return {
            'pullback_triggered': True,
            'trigger_type': res_4['rule_code'],
            'order_type': 'market',
            'reason': f"{res_4['reason']} [Macro: {macro_eval['summary_reason']}]",
            'recommended_sl': rec_sl,
            'target_upper5': round(target_u5, 2),
            'target_upper6': round(target_u6, 2),
            'macro_details': macro_eval,
            'limit_orders': []
        }

    # ════════════════════════════════════════════════════════════════
    # GATILLO ADICIONAL: Absorción directa en LOWER_5 o LOWER_6
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

    return {
        'pullback_triggered': False,
        'trigger_type': None,
        'order_type': None,
        'reason': f"En espera de gatillo 3a o 4a-4d (${current_price:.2f} vs EMA9_5m=${ema9_5m:.2f})",
        'recommended_sl': rec_sl,
        'target_upper5': round(target_u5, 2),
        'target_upper6': round(target_u6, 2),
        'macro_details': macro_eval,
        'limit_orders': []
    }
