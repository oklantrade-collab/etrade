import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

MODULE = "REBOTE_ADUANA"

def _safe_float(val, default=0.0):
    try:
        return float(val) if not pd.isna(val) else default
    except (ValueError, TypeError):
        return default

def calculate_signal_rebote_cascada_multitf(df_lower: pd.DataFrame, df_higher: pd.DataFrame, direction: str, higher_tf: str = "30m", params: dict = None) -> dict:
    """
    Estrategia REBOTE Multi-Temporalidad (30m y 15m).
    
    Condiciones LONG:
    1. Lower TF (5m/15m): EMA3 < EMA9 < EMA20 < EMA50
    2. Higher TF (30m/15m): Condición OR de Bollinger (Doble penetración o Clímax previo + Giro verde)
    3. Higher TF: Vela Verde (Close > Open) con SIPV BUY / Mecha >= 20% / Cuerpo >= 50%
    4. Higher TF: Pendiente EMA3 > 0
    5. Higher TF: Curvatura Bollinger estabilizada
    
    Condiciones SHORT:
    1. Lower TF: EMA3 > EMA9 > EMA20 > EMA50
    2. Higher TF: Condición OR de Bollinger (Doble penetración o Clímax previo + Giro rojo)
    3. Higher TF: Vela Roja (Close < Open) con SIPV SELL / Mecha >= 20% / Cuerpo >= 50%
    4. Higher TF: Pendiente EMA3 < 0
    5. Higher TF: Curvatura Bollinger estabilizada
    """
    params = params or {}
    tf_label = higher_tf.upper()
    result = {
        'score': 0,
        'triggered': False,
        'components': {},
        'detail': ''
    }

    if df_lower is None or df_lower.empty or len(df_lower) < 2:
        result['detail'] = f'Datos insuficientes en temporalidad menor para {tf_label}'
        return result

    if df_higher is None or df_higher.empty or len(df_higher) < 2:
        result['detail'] = f'Datos insuficientes en {tf_label}'
        return result

    # ── Asegurar indicadores en Lower TF ──
    df_low = df_lower.copy()
    for span, col in [(3, 'ema_3'), (9, 'ema_9'), (20, 'ema_20'), (50, 'ema_50')]:
        if col not in df_low.columns:
            df_low[col] = df_low['close'].ewm(span=span, adjust=False).mean()

    # ── Asegurar indicadores en Higher TF ──
    df_high = df_higher.copy()
    if 'ema_3' not in df_high.columns:
        df_high['ema_3'] = df_high['close'].ewm(span=3, adjust=False).mean()
    if 'lower_bb' not in df_high.columns or 'upper_bb' not in df_high.columns:
        basis = df_high['close'].rolling(20).mean()
        std = df_high['close'].rolling(20).std()
        df_high['basis'] = basis
        df_high['upper_bb'] = basis + (2.0 * std)
        df_high['lower_bb'] = basis - (2.0 * std)

    closed_lower = df_low.iloc[:-1] if len(df_low) > 1 else df_low
    closed_higher = df_high.iloc[:-1] if len(df_high) > 2 else df_high

    if len(closed_higher) < 2 or len(closed_lower) < 1:
        result['detail'] = f'Velas insuficientes para evaluar {tf_label}'
        return result

    last_low = closed_lower.iloc[-1]
    curr_high = closed_higher.iloc[-1]
    prev_high = closed_higher.iloc[-2]

    dir_upper = str(direction).upper()

    # ── 1. Evaluar Cascada en Lower TF ──
    ema3_low = _safe_float(last_low.get('ema_3'))
    ema9_low = _safe_float(last_low.get('ema_9'))
    ema20_low = _safe_float(last_low.get('ema_20'))
    ema50_low = _safe_float(last_low.get('ema_50'))

    if dir_upper == 'LONG':
        cond_cascada_lower = (ema3_low < ema9_low < ema20_low < ema50_low)
    else:
        cond_cascada_lower = (ema3_low > ema9_low > ema20_low > ema50_low)

    if not cond_cascada_lower:
        result['detail'] = f"Fallo cascada en temporalidad menor para {direction} ({tf_label})"
        return result

    # ── 2. Evaluar Bollinger en Higher TF (Variante A o B) ──
    open_curr = _safe_float(curr_high.get('open'))
    close_curr = _safe_float(curr_high.get('close'))
    low_curr = _safe_float(curr_high.get('low'))
    high_curr = _safe_float(curr_high.get('high'))
    lower_bb_curr = _safe_float(curr_high.get('lower_bb'))
    upper_bb_curr = _safe_float(curr_high.get('upper_bb'))

    open_prev = _safe_float(prev_high.get('open'))
    close_prev = _safe_float(prev_high.get('close'))
    low_prev = _safe_float(prev_high.get('low'))
    high_prev = _safe_float(prev_high.get('high'))
    lower_bb_prev = _safe_float(prev_high.get('lower_bb'))
    upper_bb_prev = _safe_float(prev_high.get('upper_bb'))

    variant_used = None

    if dir_upper == 'LONG':
        cond_var_a = (low_prev < lower_bb_prev) and (low_curr < lower_bb_curr)
        cond_var_b = (low_prev < lower_bb_prev) and (close_prev < open_prev) and (close_curr > open_curr)
        if cond_var_a: variant_used = 'DOUBLE_BB_PENETRATION'
        elif cond_var_b: variant_used = 'CLIMAX_REVERSAL_V'
    else:
        cond_var_a = (high_prev > upper_bb_prev) and (high_curr > upper_bb_curr)
        cond_var_b = (high_prev > upper_bb_prev) and (close_prev > open_prev) and (close_curr < open_curr)
        if cond_var_a: variant_used = 'DOUBLE_BB_PENETRATION'
        elif cond_var_b: variant_used = 'CLIMAX_REVERSAL_V'

    if not variant_used:
        result['detail'] = f"Fallo penetración/reversión Bollinger {tf_label} para {direction}"
        return result

    # ── 3. Vela Color / SIPV / Mecha / Cuerpo ──
    rng_high = max(high_curr - low_curr, 1e-8)
    sipv_action = "HOLD"
    try:
        from app.candle_signals.candle_patterns import CandlePatternDetector, CandleOHLC
        detector = CandlePatternDetector(market="crypto" if "USDT" in str(curr_high.get('symbol', '')) else "forex")
        c_obj = CandleOHLC(open=open_curr, high=high_curr, low=low_curr, close=close_curr, volume=_safe_float(curr_high.get('volume')))
        p_obj = CandleOHLC(open=open_prev, high=high_prev, low=low_prev, close=close_prev, volume=_safe_float(prev_high.get('volume')))
        pat_res = detector.evaluate(c_obj, history=[p_obj])
        sipv_action = pat_res.action.upper()
    except Exception:
        sipv_action = "HOLD"

    body_ratio = abs(close_curr - open_curr) / rng_high
    wick_ratio = 0.0

    if dir_upper == 'LONG':
        is_green = close_curr > open_curr
        lower_wick = min(open_curr, close_curr) - low_curr
        wick_ratio = lower_wick / rng_high
        cond_candle_valid = is_green and (sipv_action in ('BUY', 'STRONG_BUY') or wick_ratio >= 0.20 or body_ratio >= 0.50)
    else:
        is_red = close_curr < open_curr
        upper_wick = high_curr - max(open_curr, close_curr)
        wick_ratio = upper_wick / rng_high
        cond_candle_valid = is_red and (sipv_action in ('SELL', 'STRONG_SELL') or wick_ratio >= 0.20 or body_ratio >= 0.50)

    if not cond_candle_valid:
        result['detail'] = f"Fallo confirmación de vela en {tf_label} para {direction} (wick={wick_ratio:.2f}, body={body_ratio:.2f}, sipv={sipv_action})"
        return result

    # ── 4. Pendiente EMA3 en Higher TF ──
    ema3_curr = _safe_float(curr_high.get('ema_3'))
    ema3_prev = _safe_float(prev_high.get('ema_3'))

    if dir_upper == 'LONG':
        cond_ema3_slope = (ema3_curr > ema3_prev)
    else:
        cond_ema3_slope = (ema3_curr < ema3_prev)

    if not cond_ema3_slope:
        result['detail'] = f"Fallo pendiente EMA3 {tf_label} para {direction}"
        return result

    # ── 5. Curvatura de Bollinger en Higher TF ──
    bb_tol = max(0.003 * high_curr, 0.0005)
    if dir_upper == 'LONG':
        cond_bb_curve = (lower_bb_curr >= lower_bb_prev - bb_tol)
    else:
        cond_bb_curve = (upper_bb_curr <= upper_bb_prev + bb_tol)

    if not cond_bb_curve:
        result['detail'] = f"Fallo curvatura Bollinger {tf_label} para {direction}"
        return result

    # ── 6. Volumen Boost ──
    vol_boost = False
    if 'volume' in closed_higher.columns and len(closed_higher) >= 10:
        avg_vol = closed_higher['volume'].tail(10).mean()
        cur_vol = _safe_float(curr_high.get('volume'))
        if avg_vol > 0 and cur_vol > (1.2 * avg_vol):
            vol_boost = True

    base_score = params.get(f'w_rebote_cascada_{higher_tf.lower()}', 55)
    final_score = base_score + (10 if vol_boost else 0)

    result['score'] = final_score
    result['triggered'] = True
    result['components'] = {
        'cascada_lower_tf': True,
        'bb_setup_variant': variant_used,
        'sipv_action': sipv_action,
        'wick_ratio': round(wick_ratio, 3),
        'body_ratio': round(body_ratio, 3),
        'ema3_slope_valid': True,
        'bb_curve_valid': True,
        'vol_boost': vol_boost
    }
    result['detail'] = f"REBOTE CASCADA {tf_label} Triggered ({direction.upper()} | Variant: {variant_used} | Score: {final_score} | SIPV: {sipv_action} | VolBoost: {vol_boost})"
    return result
