import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

MODULE = "REBOTE_ADUANA"

def _safe_float(val, default=0.0):
    try:
        return float(val) if not pd.isna(val) else default
    except (ValueError, TypeError):
        return default

def calculate_signal_rebote_pullback_ema20(df_15m: pd.DataFrame, df_1h: pd.DataFrame, direction: str, params: dict = None) -> dict:
    """
    Estrategia REBOTE PULLBACK EMA20: Rebote de continuación sobre la media móvil en tendencia fuerte.
    
    Condiciones LONG:
    1. 15m: Tendencia alcista previa (EMA3 > EMA9 > EMA20 > EMA50)
    2. 1h: EMA20 > EMA50 (Tendencia de 1h alineada al alza)
    3. 1h: Pullback test a la EMA20 / Basis (Low_t <= Basis_t <= High_t o Low_t-1 <= Basis_t-1)
    4. 1h: Vela Verde (Close > Open) rebotando y cerrando sobre la EMA20 (Close > Basis)
    5. 1h: Giro de velocidad EMA3 (EMA3_t > EMA3_t-1)
    6. 1h: Mecha inferior >= 20% O Cuerpo de vela >= 50% O SIPV in ('BUY', 'STRONG_BUY')
    
    Condiciones SHORT (Espejo):
    1. 15m: Tendencia bajista previa (EMA3 < EMA9 < EMA20 < EMA50)
    2. 1h: EMA20 < EMA50 (Tendencia de 1h alineada a la baja)
    3. 1h: Pullback test a la EMA20 / Basis (High_t >= Basis_t >= Low_t o High_t-1 >= Basis_t-1)
    4. 1h: Vela Roja (Close < Open) rebotando y cerrando bajo la EMA20 (Close < Basis)
    5. 1h: Giro de velocidad EMA3 (EMA3_t < EMA3_t-1)
    6. 1h: Mecha superior >= 20% O Cuerpo de vela >= 50% O SIPV in ('SELL', 'STRONG_SELL')
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
    for span, col in [(3, 'ema_3'), (9, 'ema_9'), (20, 'ema_20'), (50, 'ema_50')]:
        if col not in df_15.columns:
            df_15[col] = df_15['close'].ewm(span=span, adjust=False).mean()

    # ── Asegurar indicadores en 1h ──
    df_1 = df_1h.copy()
    if 'ema_3' not in df_1.columns:
        df_1['ema_3'] = df_1['close'].ewm(span=3, adjust=False).mean()
    if 'ema_20' not in df_1.columns:
        df_1['ema_20'] = df_1['close'].ewm(span=20, adjust=False).mean()
    if 'ema_50' not in df_1.columns:
        df_1['ema_50'] = df_1['close'].ewm(span=50, adjust=False).mean()
    if 'basis' not in df_1.columns:
        df_1['basis'] = df_1['close'].rolling(20).mean()

    closed_15m = df_15.iloc[:-1] if len(df_15) > 1 else df_15
    closed_1h = df_1.iloc[:-1] if len(df_1) > 2 else df_1

    if len(closed_1h) < 2 or len(closed_15m) < 1:
        result['detail'] = 'Velas cerradas insuficientes para evaluar 1h'
        return result

    last_15 = closed_15m.iloc[-1]
    curr_1h = closed_1h.iloc[-1]
    prev_1h = closed_1h.iloc[-2]

    dir_upper = str(direction).upper()

    # ── 1. Estructura de Tendencia en 15m ──
    ema3_15 = _safe_float(last_15.get('ema_3'))
    ema9_15 = _safe_float(last_15.get('ema_9'))
    ema20_15 = _safe_float(last_15.get('ema_20'))
    ema50_15 = _safe_float(last_15.get('ema_50'))

    if dir_upper == 'LONG':
        cond_trend_15m = (ema3_15 > ema9_15 > ema20_15 > ema50_15)
    else:
        cond_trend_15m = (ema3_15 < ema9_15 < ema20_15 < ema50_15)

    if not cond_trend_15m:
        result['detail'] = f"Fallo estructura de tendencia 15m para {direction}"
        return result

    # ── 2. Tendencia Alineada en 1h ──
    ema20_1h = _safe_float(curr_1h.get('ema_20'))
    ema50_1h = _safe_float(curr_1h.get('ema_50'))
    basis_curr = _safe_float(curr_1h.get('basis')) or ema20_1h
    basis_prev = _safe_float(prev_1h.get('basis')) or _safe_float(prev_1h.get('ema_20'))

    if dir_upper == 'LONG':
        cond_trend_1h = (ema20_1h >= ema50_1h - 1e-5) or (basis_curr >= basis_prev - 1e-5)
    else:
        cond_trend_1h = (ema20_1h <= ema50_1h + 1e-5) or (basis_curr <= basis_prev + 1e-5)

    if not cond_trend_1h:
        result['detail'] = f"Fallo alineación de tendencia 1h para {direction}"
        return result

    # ── 3. Pullback Test a la Media EMA20 en 1h ──
    high_curr = _safe_float(curr_1h.get('high'))
    low_curr = _safe_float(curr_1h.get('low'))
    open_curr = _safe_float(curr_1h.get('open'))
    close_curr = _safe_float(curr_1h.get('close'))

    high_prev = _safe_float(prev_1h.get('high'))
    low_prev = _safe_float(prev_1h.get('low'))

    # Tolerancia dinámica de toque a la media
    tol = max(0.002 * high_curr, 0.0003)

    if dir_upper == 'LONG':
        pullback_tested = (low_curr <= basis_curr + tol) or (low_prev <= basis_prev + tol)
        rebound_confirmed = (close_curr > open_curr) and (close_curr >= basis_curr - tol)
    else:
        pullback_tested = (high_curr >= basis_curr - tol) or (high_prev >= basis_prev - tol)
        rebound_confirmed = (close_curr < open_curr) and (close_curr <= basis_curr + tol)

    if not (pullback_tested and rebound_confirmed):
        result['detail'] = f"Fallo test/rebote sobre EMA20 en 1h para {direction}"
        return result

    # ── 4. Giro de Velocidad EMA3 en 1h ──
    ema3_curr_1h = _safe_float(curr_1h.get('ema_3'))
    ema3_prev_1h = _safe_float(prev_1h.get('ema_3'))

    if dir_upper == 'LONG':
        cond_ema3_slope = (ema3_curr_1h > ema3_prev_1h)
    else:
        cond_ema3_slope = (ema3_curr_1h < ema3_prev_1h)

    if not cond_ema3_slope:
        result['detail'] = f"Fallo giro de velocidad EMA3 1h para {direction}"
        return result

    # ── 5. Mecha de Rechazo / Cuerpo de Convicción / SIPV ──
    rng_1h = max(high_curr - low_curr, 1e-8)
    sipv_action = "HOLD"
    try:
        from app.candle_signals.candle_patterns import CandlePatternDetector, CandleOHLC
        detector = CandlePatternDetector(market="crypto" if "USDT" in str(curr_1h.get('symbol', '')) else "forex")
        c_obj = CandleOHLC(open=open_curr, high=high_curr, low=low_curr, close=close_curr, volume=_safe_float(curr_1h.get('volume')))
        p_obj = CandleOHLC(open=_safe_float(prev_1h.get('open')), high=high_prev, low=low_prev, close=_safe_float(prev_1h.get('close')), volume=_safe_float(prev_1h.get('volume')))
        pat_res = detector.evaluate(c_obj, history=[p_obj])
        sipv_action = pat_res.action.upper()
    except Exception:
        sipv_action = "HOLD"

    body_ratio = abs(close_curr - open_curr) / rng_1h
    wick_ratio = 0.0
    if dir_upper == 'LONG':
        lower_wick = min(open_curr, close_curr) - low_curr
        wick_ratio = lower_wick / rng_1h
        cond_candle_valid = (sipv_action in ('BUY', 'STRONG_BUY')) or (wick_ratio >= 0.20) or (body_ratio >= 0.50)
    else:
        upper_wick = high_curr - max(open_curr, close_curr)
        wick_ratio = upper_wick / rng_1h
        cond_candle_valid = (sipv_action in ('SELL', 'STRONG_SELL')) or (wick_ratio >= 0.20) or (body_ratio >= 0.50)

    if not cond_candle_valid:
        result['detail'] = f"Fallo confirmación de vela en pullback EMA20 para {direction} (wick={wick_ratio:.2f}, body={body_ratio:.2f}, sipv={sipv_action})"
        return result

    # ── 6. Volumen Boost ──
    vol_boost = False
    if 'volume' in closed_1h.columns and len(closed_1h) >= 10:
        avg_vol = closed_1h['volume'].tail(10).mean()
        cur_vol = _safe_float(curr_1h.get('volume'))
        if avg_vol > 0 and cur_vol > (1.2 * avg_vol):
            vol_boost = True

    # ── Confluencia Total ──
    base_score = params.get('w_rebote_pullback_ema20', 50)
    final_score = base_score + (10 if vol_boost else 0)

    result['score'] = final_score
    result['triggered'] = True
    result['components'] = {
        'trend_15m_aligned': True,
        'trend_1h_aligned': True,
        'pullback_ema20_tested': True,
        'sipv_action': sipv_action,
        'wick_ratio': round(wick_ratio, 3),
        'body_ratio': round(body_ratio, 3),
        'ema3_slope_valid': True,
        'vol_boost': vol_boost
    }
    result['detail'] = f"REBOTE PULLBACK EMA20 Triggered ({direction.upper()} | Score: {final_score} | SIPV: {sipv_action} | VolBoost: {vol_boost})"
    return result
