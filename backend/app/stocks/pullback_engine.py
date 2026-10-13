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
# ════════════════════════════════════════════════════════════════
# 1. EVALUADORES MACRO (CONDICIONES BÁSICAS 1H a/b, ADX/DMI Y 15M)
# ════════════════════════════════════════════════════════════════

def calculate_adx_1h(df_1h: Optional[pd.DataFrame], period: int = 14) -> dict:
    """
    Calcula ADX y DMI (+DI / -DI) en temporalidad de 1 Hora:
    - ADX >= 20.0: Mercado en tendencia activa (filtra consolidación lateral).
    - +DI > -DI: Fuerza direccional alcista dominante (filtra trampas en tendencias bajistas).
    """
    if df_1h is None or len(df_1h) < period + 3:
        return {'adx': 25.0, 'plus_di': 30.0, 'minus_di': 15.0, 'is_bullish_trend': True, 'reason': 'Datos 1H mínimos'}
    try:
        h = _safe_col(df_1h, 'high').values
        l = _safe_col(df_1h, 'low').values
        c = _safe_col(df_1h, 'close').values

        tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
        up_move = h[1:] - h[:-1]
        down_move = l[:-1] - l[1:]

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        win = min(period, len(tr))
        tr_s = pd.Series(tr).rolling(win, min_periods=3).mean().values
        pdm_s = pd.Series(plus_dm).rolling(win, min_periods=3).mean().values
        mdm_s = pd.Series(minus_dm).rolling(win, min_periods=3).mean().values

        with np.errstate(divide='ignore', invalid='ignore'):
            denom = np.where(tr_s == 0, 1e-6, tr_s)
            pdi = 100.0 * (pdm_s / denom)
            mdi = 100.0 * (mdm_s / denom)
            di_sum = np.where((pdi + mdi) == 0, 1e-6, (pdi + mdi))
            dx = 100.0 * np.abs(pdi - mdi) / di_sum

        adx_s = pd.Series(dx).rolling(win, min_periods=3).mean().values
        curr_adx = float(adx_s[-1]) if not np.isnan(adx_s[-1]) else 25.0
        curr_pdi = float(pdi[-1]) if not np.isnan(pdi[-1]) else 25.0
        curr_mdi = float(mdi[-1]) if not np.isnan(mdi[-1]) else 20.0

        is_bearish_trend = (curr_adx >= 20.0 and curr_mdi > curr_pdi * 1.20)
        is_bullish = not is_bearish_trend and (curr_pdi >= curr_mdi * 0.90 or curr_adx < 22.0)
        return {
            'adx': round(curr_adx, 2),
            'plus_di': round(curr_pdi, 2),
            'minus_di': round(curr_mdi, 2),
            'is_bullish_trend': is_bullish,
            'reason': f"ADX_1H={curr_adx:.1f} (+DI={curr_pdi:.1f} vs -DI={curr_mdi:.1f})"
        }
    except Exception as e:
        return {'adx': 25.0, 'plus_di': 25.0, 'minus_di': 20.0, 'is_bullish_trend': True, 'reason': f"Fallback ADX: {e}"}


def evaluate_macro_1h_condition(df_1h: Optional[pd.DataFrame]) -> dict:
    """
    Condiciones Básicas en 1 Hora (Sección B):
      a. En temporalidad de 1 hora, EMA3 > EMA9
      b. Banda superior Bollinger ascendente y Banda inferior Bollinger descendente, en temporalidad de 1 hora
      c. Filtro Direccional ADX 1H (ADX >= 20 y +DI > -DI)
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
            'ema3_gt_ema9': False,
            'adx_info': {},
            'is_bullish_trend': True
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

        # Filtro Direccional ADX 1H
        adx_info = calculate_adx_1h(df_1h)

        passed = (cond_a or cond_b or ema3_rising) and adx_info.get('is_bullish_trend', True)
        reasons = []
        if cond_a:
            reasons.append(f"1H(a): EMA3({ema3_curr:.2f})>EMA9({ema9_curr:.2f})")
        if cond_b:
            reasons.append(f"1H(b): BB_Up↑({bb_up_slope_1h:+.3f}) & BB_Lo↓({bb_lo_slope_1h:+.3f})")
        if not reasons and ema3_rising:
            reasons.append("1H: EMA3 ascendente")
        if not adx_info.get('is_bullish_trend', True):
            reasons.append(f"ADX_1H No Alcista ({adx_info.get('reason')})")

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
            'ema3_gt_ema9': cond_a,
            'adx_info': adx_info,
            'is_bullish_trend': adx_info.get('is_bullish_trend', True)
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
    Ventana operativa optimizada para compras y recompras intradía:
    09:45 ET a 14:40 ET:
      - Evita el latigazo de apertura (09:30 - 09:44 ET: Opening Whipsaw).
      - Evita entradas tardías (>= 14:45 ET) que quedan atrapadas en ADUANA_STK_EOD_HARD_EXIT.
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
    return dt_time(9, 45) <= t <= dt_time(14, 40)


def check_vwap_support(current_price: float, vwap: float) -> bool:
    """El precio no debe estar colapsando profundamente bajo el VWAP."""
    if vwap <= 0 or current_price <= 0:
        return True
    return current_price >= (vwap * 0.985)


def evaluate_low_profit_predictor(
    current_price: float,
    recommended_sl: float,
    df_5m: Optional[pd.DataFrame],
    df_15m: Optional[pd.DataFrame],
    bands_15m: Optional[dict] = None,
    pool_type: str = 'HOT_MOMENTUM'
) -> dict:
    """
    PATRÓN PREDICTOR DE POCA GANANCIA (Room-to-Run & ATR Compression Gate):
    Bloquea la entrada en acciones comprimidas/laterales que solo ofrecen micro-ganancias (+0.3% a +0.5%)
    frente a un riesgo de Stop Loss de -1.5% a -2.5%:
      1. Room-to-Run 15m (% distancia al techo BB_Upper_15m / UPPER_3) >= 1.25% (o >= 1.65% en ALPHA_RUNNER).
      2. Ancho de Banda Bollinger 15m (BB_Width_15m) >= 1.55% y amplitud media 5m (ATR_5m %) >= 0.35%.
      3. Relación Beneficio / Riesgo (RoomToRun / StopLossDist) >= 1.30x.
    """
    if current_price <= 0 or df_5m is None or len(df_5m) < 10 or df_15m is None or len(df_15m) < 10:
        return {'passed': True, 'reason': 'Datos insuficientes para filtro de amplitud'}

    try:
        c15 = _safe_col(df_15m, 'close')
        win15 = min(20, len(c15) - 1)
        sma15 = float(c15.rolling(win15, min_periods=5).mean().iloc[-1])
        std15 = float(c15.rolling(win15, min_periods=5).std(ddof=0).fillna(0).iloc[-1])
        bb_up_15 = sma15 + 2.0 * std15
        bb_lo_15 = sma15 - 2.0 * std15
        bb_width_15_pct = ((bb_up_15 - bb_lo_15) / max(1e-6, sma15)) * 100.0

        upper3_15 = float((bands_15m or {}).get('upper_3') or bb_up_15)
        ceiling_15 = max(bb_up_15, upper3_15)
        room_to_run_pct = ((ceiling_15 - current_price) / current_price) * 100.0

        h5 = _safe_col(df_5m, 'high').iloc[-10:]
        l5 = _safe_col(df_5m, 'low').iloc[-10:]
        atr_5m_pct = float((h5 - l5).mean() / current_price * 100.0)

        risk_pct = max(0.35, ((current_price - recommended_sl) / current_price) * 100.0)
        reward_to_risk = room_to_run_pct / risk_pct

        is_alpha = str(pool_type or '').upper() == 'ALPHA_RUNNER'
        min_room = 1.65 if is_alpha else 1.25

        if bb_width_15_pct < 1.55 or atr_5m_pct < 0.35:
            return {
                'passed': False,
                'reason': f"SKIP_LOW_PROFIT_COMPRESSION: BB_Width_15m={bb_width_15_pct:.2f}% (<1.55%) o ATR_5m={atr_5m_pct:.2f}% (<0.35%)",
                'room_to_run_pct': round(room_to_run_pct, 2),
                'reward_to_risk': round(reward_to_risk, 2),
            }

        if room_to_run_pct < min_room:
            return {
                'passed': False,
                'reason': f"SKIP_LOW_ROOM_TO_RUN: Recorrido al techo 15m={room_to_run_pct:.2f}% (<{min_room:.2f}%)",
                'room_to_run_pct': round(room_to_run_pct, 2),
                'reward_to_risk': round(reward_to_risk, 2),
            }

        if reward_to_risk < 1.30:
            return {
                'passed': False,
                'reason': f"SKIP_LOW_REWARD_RISK: Ratio R/R={reward_to_risk:.2f}x (<1.30x, Room={room_to_run_pct:.2f}% vs Risk={risk_pct:.2f}%)",
                'room_to_run_pct': round(room_to_run_pct, 2),
                'reward_to_risk': round(reward_to_risk, 2),
            }

        return {
            'passed': True,
            'reason': f"Potencial Validado (Room={room_to_run_pct:.2f}%, R/R={reward_to_risk:.2f}x, BB_Width={bb_width_15_pct:.2f}%)",
            'room_to_run_pct': round(room_to_run_pct, 2),
            'reward_to_risk': round(reward_to_risk, 2),
        }
    except Exception as e:
        log_warning(MODULE, f"Error en evaluate_low_profit_predictor: {e}")
        return {'passed': True, 'reason': 'Fallback predictor'}


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
    REGLA 3a (SECCIÓN B.3 — REINGENIERÍA CON CONFIRMACIÓN DE GIRO EN 2 VELAS):
    - En temporalidad de 1 hora: EMA3_1H > EMA9_1H, Precio OPEN <= EMA3_1H y soporte EMA9_1H intacto.
    - En 15m: EMA3_15m >= EMA9_15m * 0.998 (evita cuchillos en caída libre de 15m).
    - En 5m: Vela previa tocó BB_Lower / LOWER_5 / LOWER_6 con mecha >= 25% y vela actual cierra
      verde (Close > Open), superando EMA3_5m y el cierre previo.
    """
    if df_5m is None or len(df_5m) < 6 or df_15m is None or len(df_15m) < 6:
        return {'triggered': False, 'reason': 'Datos 5m/15m insuficientes para 3a'}

    try:
        ema3_1h = float(cond_1h.get('ema3') or 0.0)
        ema9_1h = float(cond_1h.get('ema9') or 0.0)
        open_1h = float(cond_1h.get('open_1h') or 0.0)
        low_1h = float(cond_1h.get('low_1h') or 0.0)

        # Exigir tendencia 1H EMA3 > EMA9 estricta
        if not cond_1h.get('cond_a_ema3_gt_ema9'):
            return {'triggered': False, 'reason': '1H sin EMA3_1H > EMA9_1H para Regla 3a'}

        # Verificar en 15m que no esté en caída libre
        c15 = _safe_col(df_15m, 'close')
        ema3_15 = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
        ema9_15 = float(c15.ewm(span=9, adjust=False).mean().iloc[-1])
        if ema3_15 < ema9_15 * 0.998:
            return {'triggered': False, 'reason': '15m en caída libre (EMA3_15m < EMA9_15m)'}

        # Condición 3 en 1H: Open_1H <= EMA3_1H y sobre EMA9_1H
        cond_3_1h = (ema3_1h > 0) and (open_1h <= ema3_1h * 1.001 or low_1h <= ema3_1h * 1.001) and (current_price >= ema9_1h)
        if not cond_3_1h:
            return {'triggered': False, 'reason': f"1H Open (${open_1h:.2f}) > EMA3_1H (${ema3_1h:.2f}) o bajo EMA9_1H"}

        c5 = _safe_col(df_5m, 'close')
        o5 = _safe_col(df_5m, 'open')
        h5 = _safe_col(df_5m, 'high')
        l5 = _safe_col(df_5m, 'low')

        win5 = min(20, len(c5) - 1)
        sma5 = c5.rolling(win5, min_periods=5).mean()
        std5 = c5.rolling(win5, min_periods=5).std(ddof=0).fillna(0)
        bb_lo_5 = sma5 - 2.0 * std5
        ema3_5 = float(c5.ewm(span=3, adjust=False).mean().iloc[-1])

        from app.strategy.panic_recovery_gate import calculate_fibonacci_bands
        fib_5m = calculate_fibonacci_bands(df_5m, current_price)
        lower5_5m = float(fib_5m.get('lower_5') or 0.0)
        lower6_5m = float(fib_5m.get('lower_6') or 0.0)

        lower5_15m = float((bands_15m or {}).get('lower_5') or 0.0)
        lower6_15m = float((bands_15m or {}).get('lower_6') or 0.0)

        recent_low_5m = min(float(l5.iloc[-1]), float(l5.iloc[-2]))
        recent_close_5m = min(float(c5.iloc[-1]), float(c5.iloc[-2]))
        bb_lo_5_val = float(bb_lo_5.iloc[-1])

        close_lt_bb_lower = (bb_lo_5_val > 0 and recent_close_5m < bb_lo_5_val)
        low_lt_lower5 = (lower5_5m > 0 and recent_low_5m <= lower5_5m) or (lower5_15m > 0 and recent_low_5m <= lower5_15m)
        low_lt_lower6 = (lower6_5m > 0 and recent_low_5m <= lower6_5m) or (lower6_15m > 0 and recent_low_5m <= lower6_15m)

        if not (close_lt_bb_lower or low_lt_lower5 or low_lt_lower6):
            return {'triggered': False, 'reason': 'Sin extremo en 5m/15m (Close < BB_Lower o Low < LOWER_5/6)'}

        # Confirmación de giro en 2 velas: mecha de absorción >= 25% y vela actual verde cerrando sobre EMA3_5m y sobre BB_Lower_5m
        o_cur, h_cur, l_cur, c_cur = float(o5.iloc[-1]), float(h5.iloc[-1]), float(l5.iloc[-1]), float(c5.iloc[-1])
        o_prev, h_prev, l_prev, c_prev = float(o5.iloc[-2]), float(h5.iloc[-2]), float(l5.iloc[-2]), float(c5.iloc[-2])
        rng_cur = max(1e-6, h_cur - l_cur)
        rng_prev = max(1e-6, h_prev - l_prev)
        wick_cur = (max(0.0, min(o_cur, c_cur) - l_cur) / rng_cur) * 100.0
        wick_prev = (max(0.0, min(o_prev, c_prev) - l_prev) / rng_prev) * 100.0
        max_wick = max(wick_cur, wick_prev)
        body_pct = ((c_cur - o_cur) / rng_cur) * 100.0

        is_confirmed_reversal = (
            (c_cur > o_cur)
            and (body_pct >= 35.0)
            and (max_wick >= 25.0)
            and (c_cur > c_prev)
            and (current_price >= ema3_5)
            and (bb_lo_5_val <= 0 or c_cur > bb_lo_5_val)
        )

        if not is_confirmed_reversal:
            return {'triggered': False, 'reason': 'Tocó banda inferior pero sin giro confirmado en 2 velas'}

        sub_tag = "LOW<LOWER_6" if low_lt_lower6 else ("LOW<LOWER_5" if low_lt_lower5 else "CLOSE<BB_LOWER")
        return {
            'triggered': True,
            'rule_code': 'PULLBACK_3A_EMA3_1H_DIP',
            'reason': f"Regla 3a Confirmada: 1H Open/Low <= EMA3_1H (${ema3_1h:.2f}) + {sub_tag} con giro 2-Bar ({max_wick:.1f}% mecha)"
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
      - 4c: Giro confirmado en 2 velas tras tocar (Banda Inferior Bollinger - Delta) en 5m.
      - 4d: Según SIPV aparece una vela de cambio de tendencia alcista cuando el precio está
            en cualquiera de las bandas Fibonacci BASIS, UPPER_1, UPPER_2, UPPER_3 en 15m.
    """
    if df_5m is None or len(df_5m) < 6 or df_15m is None or len(df_15m) < 6:
        return {'triggered': False, 'reason': 'Datos 5m/15m insuficientes para Regla 4'}

    try:
        ema9_1h = float(cond_1h.get('ema9') or 0.0)
        ema20_1h = float(cond_1h.get('ema20') or 0.0)
        low_1h = float(cond_1h.get('low_1h') or current_price)

        near_ema9_1h = (ema9_1h > 0) and (low_1h <= ema9_1h * 1.025 or abs(current_price - ema9_1h) / ema9_1h <= 0.025) and (current_price >= ema9_1h * 0.988)
        near_ema20_1h = (ema20_1h > 0) and (low_1h <= ema20_1h * 1.025 or abs(current_price - ema20_1h) / ema20_1h <= 0.025) and (current_price >= ema20_1h * 0.990)
        in_1h_support_zone = near_ema9_1h or near_ema20_1h or (cond_1h.get('passed', False) and ema20_1h > 0 and current_price >= ema20_1h * 0.992)

        if not in_1h_support_zone:
            return {'triggered': False, 'reason': f"Precio (${current_price:.2f}) fuera de zona de rebote EMA9_1H (${ema9_1h:.2f}) / EMA20_1H (${ema20_1h:.2f})"}

        support_label = "EMA9_1H" if near_ema9_1h else ("EMA20_1H" if near_ema20_1h else "1H_BULL_ZONE")

        # ── VERIFICACIÓN ADX 1H: Tendencia estructural activa y alcista (+DI > -DI) ──
        adx_1h = cond_1h.get('adx_info', {})
        if adx_1h and not adx_1h.get('is_bullish_trend', True):
            return {'triggered': False, 'reason': f"Filtro ADX 1H No Alcista: {adx_1h.get('reason')}"}

        # Bandas Fibonacci en 15m
        from app.strategy.panic_recovery_gate import calculate_fibonacci_bands
        fib_15 = bands_15m if (bands_15m and bands_15m.get('upper_3')) else calculate_fibonacci_bands(df_15m, current_price)
        basis_15 = float(fib_15.get('basis') or current_price * 0.98)
        upper3_15 = float(fib_15.get('upper_3') or current_price * 1.05)

        dist_upper3_pct = ((upper3_15 - current_price) / current_price * 100.0) if upper3_15 > 0 else 99.0
        below_upper3 = (upper3_15 <= 0) or (dist_upper3_pct >= 1.20)

        c5 = _safe_col(df_5m, 'close')
        o5 = _safe_col(df_5m, 'open')
        h5 = _safe_col(df_5m, 'high')
        l5 = _safe_col(df_5m, 'low')
        v5 = _safe_col(df_5m, 'volume')

        c15 = _safe_col(df_15m, 'close')
        o15 = _safe_col(df_15m, 'open')
        h15 = _safe_col(df_15m, 'high')
        l15 = _safe_col(df_15m, 'low')

        ema3_15_s = c15.ewm(span=3, adjust=False).mean()
        ema9_15_s = c15.ewm(span=9, adjust=False).mean()

        # Cálculo de RVOL_5m (vs media de 10 periodos) y ATR_5m
        rvol_5m = 1.0
        if len(v5) >= 10:
            mean_v = float(v5.iloc[-10:-1].mean())
            rvol_5m = float(v5.iloc[-1]) / max(1.0, mean_v)

        atr_5m = float((h5 - l5).iloc[-14:].mean()) if len(h5) >= 14 else (current_price * 0.01)
        candle_rng_5m = float(h5.iloc[-1] - l5.iloc[-1])

        # ── SUB-REGLA 4a: Señal PINESCRIPT "BUY" + Holgura UPPER_3 >= 1.5% + RVOL_5m >= 1.2x ──
        pine_buy = str(pinescript_signal or '').upper() == 'BUY'
        if not pine_buy:
            if float(ema3_15_s.iloc[-1]) > float(ema9_15_s.iloc[-1]) and float(c15.iloc[-1]) > float(o15.iloc[-1]) and (near_ema9_1h or near_ema20_1h):
                pine_buy = True

        has_room_4a = (upper3_15 <= 0) or (dist_upper3_pct >= 1.50)
        has_vol_4a = (rvol_5m >= 1.20) or (len(v5) < 10)

        if pine_buy and has_room_4a and has_vol_4a and (near_ema9_1h or near_ema20_1h):
            return {
                'triggered': True,
                'rule_code': 'PULLBACK_4A_EMA1H_PINE_BUY',
                'reason': (
                    f"Regla 4a Activa: Rebote en {support_label} + PineScript BUY + "
                    f"Holgura UPPER_3 (+{dist_upper3_pct:.2f}% >= 1.5%) + RVOL_5m {rvol_5m:.2f}x >= 1.2x"
                )
            }

        # ── SUB-REGLA 4b: Cruce fresco EMA3 > EMA9 con Separación Angular >= 0.10% y Filtro Anti-Clímax ──
        ema3_5 = c5.ewm(span=3, adjust=False).mean()
        ema9_5 = c5.ewm(span=9, adjust=False).mean()
        ema3_5_val = float(ema3_5.iloc[-1])
        ema9_5_val = float(ema9_5.iloc[-1])
        angle_5m_pct = ((ema3_5_val - ema9_5_val) / max(1e-6, ema9_5_val)) * 100.0

        cross_5m = (ema3_5_val > ema9_5_val) and (
            float(ema3_5.iloc[-2]) <= float(ema9_5.iloc[-2]) or (len(ema3_5) >= 3 and float(ema3_5.iloc[-3]) <= float(ema9_5.iloc[-3]))
        ) and (float(c5.iloc[-1]) > float(o5.iloc[-1])) and (angle_5m_pct >= 0.10)

        ema3_15_val = float(ema3_15_s.iloc[-1])
        ema9_15_val = float(ema9_15_s.iloc[-1])
        angle_15m_pct = ((ema3_15_val - ema9_15_val) / max(1e-6, ema9_15_val)) * 100.0

        cross_15m = (ema3_15_val > ema9_15_val) and (
            float(ema3_15_s.iloc[-2]) <= float(ema9_15_s.iloc[-2]) or (len(ema3_15_s) >= 3 and float(ema3_15_s.iloc[-3]) <= float(ema9_15_s.iloc[-3]))
        ) and (float(c15.iloc[-1]) > float(o15.iloc[-1])) and (angle_15m_pct >= 0.10)

        # Filtro Anti-Sobreextensión (Vela no debe exceder 1.8 * ATR_5m)
        not_overextended = candle_rng_5m <= (1.80 * atr_5m)

        if (cross_5m or cross_15m) and below_upper3 and not_overextended:
            tf_str = "5m" if cross_5m else "15m"
            ang_val = angle_5m_pct if cross_5m else angle_15m_pct
            return {
                'triggered': True,
                'rule_code': 'PULLBACK_4B_EMA1H_CROSS_3_9',
                'reason': (
                    f"Regla 4b Activa: Rebote en {support_label} + Cruce fresco EMA3 > EMA9 en {tf_str} "
                    f"(Ángulo {ang_val:+.2f}% >= 0.10%, Vela {candle_rng_5m:.2f} <= 1.8x ATR {atr_5m:.2f}, < UPPER_3 ${upper3_15:.2f})"
                )
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

        # ── SUB-REGLA 4c (REINGENIERÍA 2-BAR REVERSAL): Toque en (BB_Lower_5m - Delta) + Giro Confirmado ──
        win5 = min(20, len(c5) - 1)
        sma5 = c5.rolling(win5, min_periods=5).mean()
        std5 = c5.rolling(win5, min_periods=5).std(ddof=0).fillna(0)
        bb_lo_5 = float((sma5 - 2.0 * std5).iloc[-1])
        delta_5 = max(0.01, (spread * 0.5) + (current_price * 0.001))
        o_cur, h_cur, l_cur, c_cur = float(o5.iloc[-1]), float(h5.iloc[-1]), float(l5.iloc[-1]), float(c5.iloc[-1])
        o_prev, h_prev, l_prev, c_prev = float(o5.iloc[-2]), float(h5.iloc[-2]), float(l5.iloc[-2]), float(c5.iloc[-2])
        rng_cur = max(1e-6, h_cur - l_cur)
        rng_prev = max(1e-6, h_prev - l_prev)
        wick_cur = (max(0.0, min(o_cur, c_cur) - l_cur) / rng_cur) * 100.0
        wick_prev = (max(0.0, min(o_prev, c_prev) - l_prev) / rng_prev) * 100.0
        max_wick = max(wick_cur, wick_prev)
        body_cur_pct = ((c_cur - o_cur) / rng_cur) * 100.0

        # Exigir:
        # 1) 1H EMA3 > EMA9 y 15m EMA3 >= EMA9 * 0.998
        # 2) Vela previa tocó BB_Lower_5m - Delta con mecha >= 25%
        # 3) Vela actual es verde con cuerpo >= 35%, cierra DENTRO de la banda (> BB_Lower_5m) y sobre EMA3_5m
        touched_bb_low = bb_lo_5 > 0 and (l_prev <= (bb_lo_5 - delta_5) * 1.002 or l_cur <= (bb_lo_5 - delta_5) * 1.002)
        confirmed_4c = (
            touched_bb_low
            and cond_1h.get('cond_a_ema3_gt_ema9', False)
            and float(ema3_15_s.iloc[-1]) >= float(ema9_15_s.iloc[-1]) * 0.998
            and max_wick >= 25.0
            and c_cur > o_cur
            and body_cur_pct >= 35.0
            and c_cur > bb_lo_5
            and c_cur > c_prev
            and current_price >= float(ema3_5.iloc[-1])
        )
        if confirmed_4c and below_upper3:
            return {
                'triggered': True,
                'rule_code': 'PULLBACK_4C_EMA1H_BB5M_LOWER',
                'reason': f"Regla 4c Confirmada: Rebote en {support_label} + Toque (BB_Lower_5m ${bb_lo_5:.2f} - Δ) con Giro 2-Bar ({max_wick:.1f}% mecha)"
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
    [DEPRECATED EN V3.0] — Mantenido solo por compatibilidad de firma; desactivado como gatillo autónomo
    debido a que generaba 61.9% de tasa de STOP_LOSS_INITIAL cuando compraba sin estructura de 1H.
    """
    return {'triggered': False, 'reason': 'PULLBACK_LOWER_ABSORPTION desactivado en v3.0 (requiere estructura 4a/4b/4d)'}


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
    pool_type: str = 'HOT_MOMENTUM',
) -> dict:
    """
    EVALUADOR MAESTRO DE COMPRAS Y RECOMPRAS (SECCIÓN B: 4a, 4b, 4d, y versiones blindadas 3a/4c)
    Incorpora el Predictor de Poca Ganancia (Room-to-Run & ATR Compression Gate).
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

    # 1. Filtro Horario (09:45 a 14:40 ET — Evita Opening Whipsaw y EOD Hard Exit)
    if not is_in_pullback_time_window(now_dt):
        return {
            'pullback_triggered': False,
            'trigger_type': None,
            'order_type': None,
            'reason': 'Fuera de ventana operativa óptima (09:45 ET a 14:40 ET)',
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

    # 3. Objetivos y Stop Loss Inicial Dinámico por Volatilidad (1.5 * ATR_14_5m bajo Anchor Low)
    target_u5 = float(bands_15m.get('upper_5', current_price * 1.05)) if bands_15m else current_price * 1.05
    target_u6 = float(bands_15m.get('upper_6', current_price * 1.08)) if bands_15m else current_price * 1.08

    ema9_5m = current_price
    ema20_5m = current_price
    if df_5m is not None and len(df_5m) >= 10:
        c_5m = _safe_col(df_5m, 'close')
        h_5m = _safe_col(df_5m, 'high')
        l_5m = _safe_col(df_5m, 'low')
        ema9_5m = float(c_5m.ewm(span=9, adjust=False).mean().iloc[-1])
        ema20_5m = float(c_5m.ewm(span=20, adjust=False).mean().iloc[-1])
        atr_5m_val = float((h_5m - l_5m).iloc[-14:].mean()) if len(h_5m) >= 14 else (current_price * 0.01)
        anchor_low = float(min(l_5m.iloc[-3:].min(), current_price))
        raw_sl = anchor_low - (1.50 * atr_5m_val)
        min_sl = current_price * 0.9675  # -3.25% Máximo riesgo tolerado
        max_sl = current_price * 0.9900  # -1.00% Mínimo espacio para respirar
        rec_sl = round(max(min_sl, min(max_sl, raw_sl)), 2)
    else:
        rec_sl = round(current_price * 0.98, 2)

    # 4. Aduana Predictora de Poca Ganancia (Room-to-Run & ATR Compression Gate)
    profit_pred = evaluate_low_profit_predictor(
        current_price=current_price,
        recommended_sl=rec_sl,
        df_5m=df_5m,
        df_15m=df_15m,
        bands_15m=bands_15m,
        pool_type=pool_type,
    )
    if not profit_pred.get('passed', True):
        return {
            'pullback_triggered': False,
            'trigger_type': None,
            'order_type': None,
            'reason': profit_pred.get('reason', 'Bloqueado por Predictor de Poca Ganancia'),
            'recommended_sl': rec_sl,
            'target_upper5': round(target_u5, 2),
            'target_upper6': round(target_u6, 2),
            'macro_details': macro_eval,
            'limit_orders': []
        }

    cond_1h = macro_eval.get('cond_a', {})

    # ════════════════════════════════════════════════════════════════
    # PRIORIDAD 1 — REGLA 4 (4a, 4b, 4d, y 4c 2-Bar): Rebote en EMA9 o EMA20 de 1 Hora
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
            'reason': f"{res_4['reason']} | {profit_pred['reason']}",
            'recommended_sl': rec_sl,
            'target_upper5': round(target_u5, 2),
            'target_upper6': round(target_u6, 2),
            'macro_details': macro_eval,
            'limit_orders': []
        }

    # ════════════════════════════════════════════════════════════════
    # PRIORIDAD 2 — REGLA 3a (Confirmación 2-Bar): Open_1H <= EMA3_1H + Giro en Banda Inferior
    # ════════════════════════════════════════════════════════════════
    res_3a = evaluate_rule_3a_ema3_1h_dip(current_price, cond_1h, df_5m, df_15m, bands_15m)
    if res_3a.get('triggered'):
        return {
            'pullback_triggered': True,
            'trigger_type': res_3a['rule_code'],
            'order_type': 'market',
            'reason': f"{res_3a['reason']} | {profit_pred['reason']}",
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
        'reason': f"En espera de gatillo 4a/4b/4d/3a (${current_price:.2f} vs EMA9_5m=${ema9_5m:.2f})",
        'recommended_sl': rec_sl,
        'target_upper5': round(target_u5, 2),
        'target_upper6': round(target_u6, 2),
        'macro_details': macro_eval,
        'limit_orders': []
    }
