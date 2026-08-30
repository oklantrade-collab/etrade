import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

MODULE = "REBOTE_ADUANA"

def _safe_float(val, default=0.0):
    try:
        return float(val) if not pd.isna(val) else default
    except (ValueError, TypeError):
        return default

def calculate_signal_rebote_cascada_1h(df_15m: pd.DataFrame, df_1h: pd.DataFrame, direction: str, params: dict = None) -> dict:
    """
    Estrategia REBOTE: Cascada 15m + Perforación Bollinger 1h (Variante A o B) + SIPV / Giro al cierre.
    
    Condiciones LONG:
    1. 15m: EMA3 < EMA9 < EMA20 < EMA50 < EMA200
    2. 1h (Condición OR de Bollinger):
       - Variante A (Doble penetración): LOW(t-1) < Lower_BB(t-1) AND LOW(t) < Lower_BB(t)
       - Variante B (Clímax previo + Giro verde): LOW(t-1) < Lower_BB(t-1) AND Vela(t-1) Roja AND Vela(t) Verde
    3a. 1h: Vela Verde (Close > Open) AND (SIPV in ('BUY', 'STRONG_BUY') OR Mecha Inferior >= 30% del rango)
    3b. 1h: Pendiente EMA3 > 0 (EMA3_t > EMA3_t-1)
    3c. 1h: Curvatura Banda Inferior de Bollinger (Lower_BB_t >= Lower_BB_t-1 - tolerancia)
    4. ADX Filter: Si ADX_1h > 50 -> Exige EMA3 > EMA9 en 15m
    5. Volume Boost: Si Vol_1h > 1.2 * Avg_Vol_10 -> Bonificación de confianza (+10 score)
    
    Condiciones SHORT (Espejo):
    1. 15m: EMA3 > EMA9 > EMA20 > EMA50 > EMA200
    2. 1h (Condición OR de Bollinger):
       - Variante A (Doble penetración): HIGH(t-1) > Upper_BB(t-1) AND HIGH(t) > Upper_BB(t)
       - Variante B (Clímax previo + Giro rojo): HIGH(t-1) > Upper_BB(t-1) AND Vela(t-1) Verde AND Vela(t) Roja
    3a. 1h: Vela Roja (Close < Open) AND (SIPV in ('SELL', 'STRONG_SELL') OR Mecha Superior >= 30% del rango)
    3b. 1h: Pendiente EMA3 < 0 (EMA3_t < EMA3_t-1)
    3c. 1h: Curvatura Banda Superior de Bollinger (Upper_BB_t <= Upper_BB_t-1 + tolerancia)
    4. ADX Filter: Si ADX_1h > 50 -> Exige EMA3 < EMA9 en 15m
    """
    params = params or {}
    result = {
        'score': 0,
        'triggered': False,
        'components': {},
        'detail': ''
    }

    if df_15m is None or df_15m.empty or len(df_15m) < 2:
        result['detail'] = 'Datos insuficientes en 15m'
        return result

    if df_1h is None or df_1h.empty or len(df_1h) < 2:
        result['detail'] = 'Datos insuficientes en 1h'
        return result

    # ── Asegurar indicadores en 15m ──
    df_15 = df_15m.copy()
    for span, col in [(3, 'ema_3'), (9, 'ema_9'), (20, 'ema_20'), (50, 'ema_50'), (200, 'ema_200')]:
        if col not in df_15.columns:
            df_15[col] = df_15['close'].ewm(span=span, adjust=False).mean()

    # ── Asegurar indicadores en 1h ──
    df_1 = df_1h.copy()
    if 'ema_3' not in df_1.columns:
        df_1['ema_3'] = df_1['close'].ewm(span=3, adjust=False).mean()
    if 'lower_bb' not in df_1.columns or 'upper_bb' not in df_1.columns:
        basis = df_1['close'].rolling(20).mean()
        std = df_1['close'].rolling(20).std()
        df_1['basis'] = basis
        df_1['upper_bb'] = basis + (2.0 * std)
        df_1['lower_bb'] = basis - (2.0 * std)

    # Considerar últimas velas cerradas
    closed_15m = df_15.iloc[:-1] if len(df_15) > 1 else df_15
    closed_1h = df_1.iloc[:-1] if len(df_1) > 2 else df_1

    if len(closed_1h) < 2 or len(closed_15m) < 1:
        result['detail'] = 'Velas cerradas insuficientes para evaluar 1h'
        return result

    last_15 = closed_15m.iloc[-1]
    curr_1h = closed_1h.iloc[-1]
    prev_1h = closed_1h.iloc[-2]

    dir_upper = str(direction).upper()

    # ── 1. Evaluar Cascada 15m ──
    ema3_15 = _safe_float(last_15.get('ema_3'))
    ema9_15 = _safe_float(last_15.get('ema_9'))
    ema20_15 = _safe_float(last_15.get('ema_20'))
    ema50_15 = _safe_float(last_15.get('ema_50'))
    ema200_15 = _safe_float(last_15.get('ema_200'))

    if dir_upper == 'LONG':
        cond_cascada_15m = (ema3_15 < ema9_15 < ema20_15 < ema50_15 < ema200_15)
    else:
        cond_cascada_15m = (ema3_15 > ema9_15 > ema20_15 > ema50_15 > ema200_15)

    if not cond_cascada_15m:
        result['detail'] = f"Fallo cascada 15m para {direction}"
        return result

    # ── 2. Evaluar Bollinger 1h con Condición OR (Variante A o Variante B) ──
    open_curr_1h = _safe_float(curr_1h.get('open'))
    close_curr_1h = _safe_float(curr_1h.get('close'))
    low_curr_1h = _safe_float(curr_1h.get('low'))
    high_curr_1h = _safe_float(curr_1h.get('high'))
    lower_bb_curr = _safe_float(curr_1h.get('lower_bb'))
    upper_bb_curr = _safe_float(curr_1h.get('upper_bb'))

    open_prev_1h = _safe_float(prev_1h.get('open'))
    close_prev_1h = _safe_float(prev_1h.get('close'))
    low_prev_1h = _safe_float(prev_1h.get('low'))
    high_prev_1h = _safe_float(prev_1h.get('high'))
    lower_bb_prev = _safe_float(prev_1h.get('lower_bb'))
    upper_bb_prev = _safe_float(prev_1h.get('upper_bb'))

    variant_used = None

    if dir_upper == 'LONG':
        # Variante A: Doble penetración
        cond_var_a = (low_prev_1h < lower_bb_prev) and (low_curr_1h < lower_bb_curr)
        # Variante B: Penetración previa de clímax bajista + Giro verde inmediato en la actual
        cond_var_b = (low_prev_1h < lower_bb_prev) and (close_prev_1h < open_prev_1h) and (close_curr_1h > open_curr_1h)

        if cond_var_a:
            variant_used = 'DOUBLE_BB_PENETRATION'
        elif cond_var_b:
            variant_used = 'CLIMAX_REVERSAL_V'
    else:
        # Variante A: Doble penetración
        cond_var_a = (high_prev_1h > upper_bb_prev) and (high_curr_1h > upper_bb_curr)
        # Variante B: Penetración previa de clímax alcista + Giro rojo inmediato en la actual
        cond_var_b = (high_prev_1h > upper_bb_prev) and (close_prev_1h > open_prev_1h) and (close_curr_1h < open_curr_1h)

        if cond_var_a:
            variant_used = 'DOUBLE_BB_PENETRATION'
        elif cond_var_b:
            variant_used = 'CLIMAX_REVERSAL_V'

    cond_bb_penetration = (variant_used is not None)
    if not cond_bb_penetration:
        result['detail'] = f"Fallo penetración/reversión Bollinger 1h (Ni Variante A ni B cumplidas para {direction})"
        return result

    # ── 3a. Vela Color + SIPV / Mecha de Rechazo ──
    rng_1h = max(high_curr_1h - low_curr_1h, 1e-8)
    sipv_action = "HOLD"
    try:
        from app.candle_signals.candle_patterns import CandlePatternDetector, CandleOHLC
        detector = CandlePatternDetector(market="crypto" if "USDT" in str(curr_1h.get('symbol', '')) else "forex")
        c_obj = CandleOHLC(open=open_curr_1h, high=high_curr_1h, low=low_curr_1h, close=close_curr_1h, volume=_safe_float(curr_1h.get('volume')))
        p_obj = CandleOHLC(open=open_prev_1h, high=high_prev_1h, low=low_prev_1h, close=close_prev_1h, volume=_safe_float(prev_1h.get('volume')))
        pat_res = detector.evaluate(c_obj, history=[p_obj])
        sipv_action = pat_res.action.upper()
    except Exception:
        sipv_action = "HOLD"

    wick_ratio = 0.0
    body_ratio = abs(close_curr_1h - open_curr_1h) / rng_1h
    if dir_upper == 'LONG':
        is_green = close_curr_1h > open_curr_1h
        lower_wick = min(open_curr_1h, close_curr_1h) - low_curr_1h
        wick_ratio = lower_wick / rng_1h
        cond_sipv_or_wick = is_green and (sipv_action in ("BUY", "STRONG_BUY") or wick_ratio >= 0.20 or body_ratio >= 0.50)
    else:
        is_red = close_curr_1h < open_curr_1h
        upper_wick = high_curr_1h - max(open_curr_1h, close_curr_1h)
        wick_ratio = upper_wick / rng_1h
        cond_sipv_or_wick = is_red and (sipv_action in ("SELL", "STRONG_SELL") or wick_ratio >= 0.20 or body_ratio >= 0.50)

    if not cond_sipv_or_wick:
        result['detail'] = f"Fallo vela/SIPV/mecha/cuerpo 1h para {direction} (is_valid_color={is_green if dir_upper=='LONG' else is_red}, sipv={sipv_action}, wick_ratio={wick_ratio:.2f}, body_ratio={body_ratio:.2f})"
        return result

    # ── 3b. Pendiente EMA3 en 1h ──
    ema3_curr_1h = _safe_float(curr_1h.get('ema_3'))
    ema3_prev_1h = _safe_float(prev_1h.get('ema_3'))

    if dir_upper == 'LONG':
        cond_ema3_slope = (ema3_curr_1h > ema3_prev_1h)
    else:
        cond_ema3_slope = (ema3_curr_1h < ema3_prev_1h)

    if not cond_ema3_slope:
        result['detail'] = f"Fallo pendiente EMA3 1h para {direction} (curr={ema3_curr_1h:.4f}, prev={ema3_prev_1h:.4f})"
        return result

    # ── 3c. Curvatura / Estabilización de Bollinger en 1h ──
    # Tolerancia proporcional al precio (0.3% del activo) para permitir absorción de volatilidad en el giro
    bb_tol = max(0.003 * high_curr_1h, 0.0005)
    if dir_upper == 'LONG':
        cond_bb_curve = (lower_bb_curr >= lower_bb_prev - bb_tol)
    else:
        cond_bb_curve = (upper_bb_curr <= upper_bb_prev + bb_tol)

    if not cond_bb_curve:
        result['detail'] = f"Fallo curvatura Bollinger 1h para {direction} (curr={lower_bb_curr if dir_upper=='LONG' else upper_bb_curr:.4f}, prev={lower_bb_prev if dir_upper=='LONG' else upper_bb_prev:.4f}, tol={bb_tol:.4f})"
        return result

    # ── 4. Filtro ADX en 1h ──
    adx_1h = _safe_float(curr_1h.get('adx', 20.0))
    if adx_1h > 50.0:
        if dir_upper == 'LONG' and ema3_15 <= ema9_15:
            result['detail'] = f"ADX 1h > 50 ({adx_1h:.1f}) requiere confirmación rápida EMA3 > EMA9 en 15m para LONG"
            return result
        elif dir_upper == 'SHORT' and ema3_15 >= ema9_15:
            result['detail'] = f"ADX 1h > 50 ({adx_1h:.1f}) requiere confirmación rápida EMA3 < EMA9 en 15m para SHORT"
            return result

    # ── 5. Volumen Boost ──
    vol_boost = False
    if 'volume' in closed_1h.columns and len(closed_1h) >= 10:
        avg_vol = closed_1h['volume'].tail(10).mean()
        cur_vol = _safe_float(curr_1h.get('volume'))
        if avg_vol > 0 and cur_vol > (1.2 * avg_vol):
            vol_boost = True

    # ── Confluencia Total Aprobada ──
    base_score = params.get('w_rebote_cascada_1h', 55)
    final_score = base_score + (10 if vol_boost else 0)

    result['score'] = final_score
    result['triggered'] = True
    result['components'] = {
        'cascada_15m': True,
        'bb_setup_variant': variant_used,
        'sipv_action': sipv_action,
        'wick_ratio': round(wick_ratio, 3),
        'ema3_slope_positive': (ema3_curr_1h > ema3_prev_1h),
        'bb_curve_valid': True,
        'vol_boost': vol_boost,
        'adx_1h': adx_1h
    }
    result['detail'] = f"REBOTE CASCADA 1H Triggered ({direction.upper()} | Variant: {variant_used} | Score: {final_score} | SIPV: {sipv_action} | VolBoost: {vol_boost})"
    return result
