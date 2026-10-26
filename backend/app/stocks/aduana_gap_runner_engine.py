"""
eTrade v6.0 — ADUANA OPEN GAP RUNNER ENGINE (STOCKS)
===================================================
Motor especializado e institucional para la detección, ranking,
compra escalonada en 3 tranches y supervisión de salidas de
activos con OPEN GAP UP en el mercado de Stocks.

Pilares del Motor:
1. Ranking Dinámico de Velocidad (5m): Tasa de aceleración porcentual por minuto (%/min).
2. Entradas Escalonadas en 3 Tranches:
   - Tranche 1 (1/3 - 33.3%): Confirmación micro 5m (Vela 1 verde + Vela 2 con micro-gap) + Macro 1H con espacio.
   - Tranche 2 (2/3 - 66.6%): Apertura de Vela 2 en 15m con presión compradora.
   - Tranche 3 (3/3 - 100%): Apertura de Vela 3 en 15m con RSI 1H <= 72.
3. Supervisión Continua de Salida ADUANA:
   - Salida defensiva ante aplanamiento/caída del ángulo de EMA3 en 1H (slope <= 0).
   - Detección de agotamiento institucional por compresión de vela (High - Low) tras perforar Banda Superior Bollinger 1H.
   - Trailing ratchet acelerado para asegurar ganancias en expansión.
"""

import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.core.logger import log_info, log_warning, log_error
from app.strategy.panic_recovery_gate import calculate_fibonacci_bands

MODULE = "ADUANA_GAP_RUNNER"


def _safe_col(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Retorna la serie de la columna en minúscula o mayúscula de forma segura."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    col = None
    if col_name in df.columns:
        col = df[col_name]
    elif col_name.capitalize() in df.columns:
        col = df[col_name.capitalize()]
    elif col_name.upper() in df.columns:
        col = df[col_name.upper()]
    elif isinstance(df.columns, pd.MultiIndex):
        for c in df.columns:
            if c[0].lower() == col_name.lower():
                col = df[c]
                break
    if col is None:
        return pd.Series(dtype=float)
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]
    return col.astype(float)


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calcula el índice RSI de Wilder."""
    if len(series) < period + 1:
        return pd.Series(50.0, index=series.index)
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    # Wilder smoothing
    for i in range(period, len(series)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss.replace(0, 1e-6)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def compute_bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0) -> Dict[str, pd.Series]:
    """Calcula Bandas de Bollinger y desviación estándar."""
    if len(series) < period:
        sma = series.rolling(window=max(1, len(series)), min_periods=1).mean()
        std = series.rolling(window=max(1, len(series)), min_periods=1).std().fillna(0.0)
    else:
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std().fillna(0.0)
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return {"basis": sma, "upper": upper, "lower": lower, "std": std}


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Calcula el VWAP intradía a partir de velas OHLCV."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    h = _safe_col(df, "high")
    l = _safe_col(df, "low")
    c = _safe_col(df, "close")
    v = _safe_col(df, "volume")
    typical_price = (h + l + c) / 3.0
    cum_vol = v.cumsum()
    cum_pv = (typical_price * v).cumsum()
    vwap = cum_pv / cum_vol.replace(0, np.nan)
    return vwap.ffill()


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calcula el Average True Range (ATR) de Wilder sobre el DataFrame."""
    if df is None or len(df) < 2:
        return 0.0
    c = _safe_col(df, "close")
    h = _safe_col(df, "high")
    l = _safe_col(df, "low")
    if len(c) < 2:
        return 0.0
    prev_c = c.shift(1).fillna(c)
    tr = np.maximum(h - l, np.maximum(abs(h - prev_c), abs(l - prev_c)))
    atr_series = tr.rolling(window=min(period, len(tr)), min_periods=1).mean()
    return float(atr_series.iloc[-1])

def compute_price_velocity_5m(df_5m: Optional[pd.DataFrame]) -> Dict[str, Any]:
    """
    Calcula la velocidad del cambio de precio cada 5 minutos y la clasifica en categorías:
    - MUY_ALTO: V_5m > +1.50%
    - ALTO:     +0.60% < V_5m <= +1.50%
    - MEDIO:    +0.15% < V_5m <= +0.60%
    - BAJO:     -0.15% <= V_5m <= +0.15%  (Estancamiento / Lateral)
    - MUY_BAJO: V_5m < -0.15%             (Deceleración o caída)
    """
    default_res = {
        "v_5m": 0.0,
        "category": "MEDIO",
        "consecutive_low": 0,
        "is_stagnant": False,
        "v_history": []
    }
    if df_5m is None or len(df_5m) < 2:
        return default_res

    c = _safe_col(df_5m, "close")
    if len(c) < 2:
        return default_res

    v_history = []
    max_lookback = min(5, len(c) - 1)
    for i in range(len(c) - max_lookback, len(c)):
        c_curr = float(c.iloc[i])
        c_prev = float(c.iloc[i - 1])
        if c_prev > 0:
            pct = ((c_curr - c_prev) / c_prev) * 100.0
        else:
            pct = 0.0
        v_history.append(pct)

    last_v = v_history[-1] if v_history else 0.0

    def categorize_velocity(val: float) -> str:
        if val > 1.50:
            return "MUY_ALTO"
        elif val > 0.60:
            return "ALTO"
        elif val > 0.15:
            return "MEDIO"
        elif val >= -0.15:
            return "BAJO"
        else:
            return "MUY_BAJO"

    cat = categorize_velocity(last_v)

    consecutive_low = 0
    for val in reversed(v_history[-3:]):
        if val <= 0.15:
            consecutive_low += 1
        else:
            break

    is_stagnant = consecutive_low >= 3

    return {
        "v_5m": round(last_v, 3),
        "category": cat,
        "consecutive_low": consecutive_low,
        "is_stagnant": is_stagnant,
        "v_history": [round(x, 3) for x in v_history]
    }


def _check_15m_rebuy_filters(
    df_15m: Optional[pd.DataFrame],
    cur_p: float
) -> Optional[str]:
    """
    Evalúa filtros institucionales de 15m antes de permitir recompras (Tranches 2 y 3):
    1. Agotamiento lateral en 15m (|Slope EMA3| <= 0.04% y Rango < 0.5 ATR).
    2. Bollinger Superior 15m: si el precio está sobre la banda:
       - Rechazar si el cuerpo de vela es comprimido (< 0.4 ATR).
       - Si RSI 15m > 70, exigir RVOL >= 2.0x y cuerpo expansivo >= 0.8 ATR.
    Retorna string con motivo de bloqueo, o None si pasa la validación.
    """
    if df_15m is None or len(df_15m) < 2:
        return None

    c15 = _safe_col(df_15m, "close")
    o15 = _safe_col(df_15m, "open")
    h15 = _safe_col(df_15m, "high")
    l15 = _safe_col(df_15m, "low")
    v15 = _safe_col(df_15m, "volume")

    atr_15m = compute_atr(df_15m, 14)
    if atr_15m <= 0:
        atr_15m = max(0.01, cur_p * 0.015)

    bb_15m = compute_bollinger_bands(c15, period=min(20, len(c15)), num_std=2.0)
    bb_upper_15m = float(bb_15m["upper"].iloc[-1])

    rsi_15m_series = compute_rsi(c15, period=min(14, len(c15) - 1))
    rsi_15m_val = float(rsi_15m_series.iloc[-1]) if len(rsi_15m_series) > 0 else 50.0

    ema3_15m_s = c15.ewm(span=3, adjust=False).mean()
    ema3_15m_now = float(ema3_15m_s.iloc[-1])
    ema3_15m_prev = float(ema3_15m_s.iloc[-2]) if len(ema3_15m_s) >= 2 else ema3_15m_now
    ema3_slope_15m = ((ema3_15m_now - ema3_15m_prev) / max(0.01, ema3_15m_prev)) * 100.0

    candle_body_15m = abs(float(c15.iloc[-1]) - float(o15.iloc[-1]))
    candle_range_15m = float(h15.iloc[-1]) - float(l15.iloc[-1])

    v15_now = float(v15.iloc[-1]) if len(v15) > 0 else 0.0
    v15_avg = float(v15.rolling(10, min_periods=1).mean().iloc[-1]) if len(v15) > 0 else 1.0
    rvol_15m = round(v15_now / max(1.0, v15_avg), 2)

    # Filtro 1: Detección de Agotamiento Lateral en 15m ("El precio no quiere subir más")
    price_change_15m = (abs(float(c15.iloc[-1]) - float(c15.iloc[-2])) / float(c15.iloc[-2])) * 100.0 if len(c15) >= 2 else 0.0
    is_lateral_slope = (abs(ema3_slope_15m) <= 0.15) or (price_change_15m <= 0.10)
    is_compressed_candle = candle_range_15m < (0.50 * atr_15m)
    if is_lateral_slope and is_compressed_candle:
        return (
            f"Agotamiento Lateral 15m detectado: EMA3 slope ({ema3_slope_15m:+.3f}%) plano y "
            f"rango vela (${candle_range_15m:.2f} < 0.5*ATR ${atr_15m:.2f}). Compras cortadas."
        )

    # Filtro 2: Bollinger Superior 15m en Recompras
    if cur_p >= bb_upper_15m:
        if candle_body_15m < (0.40 * atr_15m):
            return (
                f"Recompra bloqueada sobre Bollinger Superior 15m (${bb_upper_15m:.2f}): "
                f"Vela comprimida (Cuerpo ${candle_body_15m:.2f} < 0.4*ATR ${atr_15m:.2f}). Agotamiento de momentum."
            )

        if rsi_15m_val > 70.0:
            has_thrust = (rvol_15m >= 2.0) and (candle_body_15m >= 0.80 * atr_15m)
            if not has_thrust:
                return (
                    f"Recompra bloqueada sobre Bollinger Superior con RSI 15m ({rsi_15m_val:.1f} > 70.0): "
                    f"Exige RVOL >= 2.0x (actual {rvol_15m}x) y vela expansiva >= 0.8*ATR (actual {candle_body_15m:.2f}/{atr_15m:.2f})."
                )

    return None



def calculate_gap_velocity_ranking(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Regla 1: Recalcular el ranking de las posiciones alcistas (Open Gap Up).
    a. Tomar el precio al cierre de 5 minutos y comparar con el precio de cierre de la vela anterior de 5m.
    b. Calcular el % de incremento y dividirlo / 5 para obtener la tasa de aceleración por minuto (%/min).
    c. Ordenar el ranking descendente.
    Filtro de Liquidez: Volumen 5m >= 25,000 o RVOL 5m >= 1.5x.
    """
    ranked_list = []

    for item in candidates:
        ticker = item.get("ticker", "UNKNOWN")
        df_5m = item.get("df_5m")
        gap_pct = float(item.get("gap_pct") or 0.0)

        if df_5m is None or len(df_5m) < 2:
            continue

        c_series = _safe_col(df_5m, "close")
        v_series = _safe_col(df_5m, "volume")

        if len(c_series) < 2:
            continue

        c_now = float(c_series.iloc[-1])
        c_prev = float(c_series.iloc[-2])

        if c_prev <= 0:
            continue

        diff_price = c_now - c_prev
        diff_pct = (diff_price / c_prev) * 100.0
        rate_per_min = diff_pct / 5.0

        v_now = float(v_series.iloc[-1]) if len(v_series) > 0 else 0.0
        v_avg = float(v_series.rolling(20, min_periods=1).mean().iloc[-1]) if len(v_series) > 0 else 1.0
        rvol_5m = round(v_now / max(1.0, v_avg), 2)

        # Filtro de liquidez mínima: volumen de 5m >= 25,000 acciones o RVOL >= 1.5x
        is_liquid = (v_now >= 25000) or (rvol_5m >= 1.5) or (item.get("price", 0) * v_now >= 50000)

        ranked_list.append({
            "ticker": ticker,
            "current_price": c_now,
            "c_prev_5m": c_prev,
            "diff_price": round(diff_price, 4),
            "diff_pct": round(diff_pct, 2),
            "rate_per_min": round(rate_per_min, 4),
            "gap_pct": gap_pct,
            "volume_5m": int(v_now),
            "rvol_5m": rvol_5m,
            "is_liquid": is_liquid,
            "raw_item": item
        })

    # Ordenar ranking descendente por tasa de incremento por minuto
    ranked_list.sort(key=lambda x: (1 if x["is_liquid"] else 0, x["rate_per_min"]), reverse=True)
    return ranked_list


def _get_et_hour_min(df: pd.DataFrame) -> Optional[tuple]:
    """Extrae la hora y minuto en horario Eastern Time (ET) del último timestamp del DataFrame."""
    if df is None or df.empty:
        return None
    try:
        last_ts = df.index[-1]
        if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is not None:
            ts_et = last_ts.tz_convert("America/New_York")
            return ts_et.hour, ts_et.minute
        elif hasattr(last_ts, "hour"):
            h, m = last_ts.hour, last_ts.minute
            if h >= 13:
                return h - 4, m
            return h, m
    except Exception:
        pass
    return None


def evaluate_gap_runner_entry_tranches(
    ticker: str,
    df_5m: Optional[pd.DataFrame],
    df_15m: Optional[pd.DataFrame],
    df_1h: Optional[pd.DataFrame],
    gap_pct: float,
    active_position: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Regla 2: Seleccionar solo los OPEN GAP UP del día y evaluar entrada en 3 Tranches.
    
    2.a: Temporalidad 1H:
         - Open_1H < (Banda Superior Bollinger_1H - Delta)
         - RSI_1H < 80.0 (umbral calibrado para no asfixiar runners de apertura).
    2.b: Temporalidad 5m (Vela 1 / anterior):
         - Close_5m > Open_5m (Vela verde compradora).
    2.c: Temporalidad 5m (Vela 2 / actual):
         - Open_5m > Close_5m[vela anterior] (micro-gap) y confirmación alcista.
    2.d: Entradas progresivas en 3 Tranches:
         - Tranche 1 (1/3 = 33.3%): Cumple a, b, c en 5m.
         - Tranche 2 (2/3 = 66.6%): Cumple a + Vela 2 de 15m (Open > Close anterior).
         - Tranche 3 (3/3 = 100%): Cumple a + Vela 3 de 15m (Open > Close anterior) y RSI_1H <= 72.
    """
    res = {
        "ticker": ticker,
        "should_enter": False,
        "tranche_step": 0,
        "tranche_shares_ratio": 0.0,
        "rule_code": "",
        "initial_sl": 0.0,
        "entry_price": 0.0,
        "reason": "",
        "macro_1h_ok": False,
        "rsi_1h": 50.0,
        "room_to_bb_upper_1h": 0.0,
    }

    if df_5m is None or len(df_5m) < 2:
        res["reason"] = "Datos insuficientes en 5m (mínimo 2 velas requeridas)"
        return res

    c5 = _safe_col(df_5m, "close")
    o5 = _safe_col(df_5m, "open")
    h5 = _safe_col(df_5m, "high")
    l5 = _safe_col(df_5m, "low")
    v5 = _safe_col(df_5m, "volume")

    cur_p = float(c5.iloc[-1])
    res["entry_price"] = cur_p

    # ── PILAR 1: Ventana Horaria Estricta de Apertura (09:30 - 11:15 ET) ──
    skip_window = bool(config and config.get("skip_time_window_check"))
    if not skip_window:
        et_time = _get_et_hour_min(df_5m)
        if et_time:
            et_h, et_m = et_time
            is_late = (et_h > 11) or (et_h == 11 and et_m > 15)
            is_early = (et_h < 9) or (et_h == 9 and et_m < 30)
            if is_late or is_early:
                res["reason"] = f"Fuera de ventana de apertura institucional ({et_h:02d}:{et_m:02d} ET no está en 09:30 - 11:15 ET). Entradas en Gaps bloqueadas."
                return res

    # ── PILAR 2: Filtro Maestro Sobre VWAP en Entrada (Compras estrictamente sobre VWAP) ──
    skip_vwap = bool(config and config.get("skip_vwap_check"))
    if not skip_vwap:
        vwap_series_init = compute_vwap(df_5m)
        cur_vwap_init = float(vwap_series_init.iloc[-1]) if len(vwap_series_init) > 0 else 0.0
        if cur_vwap_init > 0 and cur_p < (cur_vwap_init * 0.999):
            res["reason"] = f"Filtro Maestro VWAP: Precio actual (${cur_p:.2f}) cotiza por debajo del VWAP (${cur_vwap_init:.2f}). Compras en largo bloqueadas bajo VWAP."
            return res

    # ─────────────────────────────────────────────────────────────
    # PASO 1: Validación Macro 1H (Regla 2.a)
    # ─────────────────────────────────────────────────────────────
    macro_1h_ok = False
    rsi_1h_val = 50.0
    room_to_bb_upper_pct = 20.0

    if df_1h is not None and len(df_1h) >= 5:
        c1h = _safe_col(df_1h, "close")
        o1h = _safe_col(df_1h, "open")
        h1h = _safe_col(df_1h, "high")
        l1h = _safe_col(df_1h, "low")

        # RSI 1H
        rsi_series_1h = compute_rsi(c1h, period=min(14, len(c1h) - 1))
        rsi_1h_val = float(rsi_series_1h.iloc[-1]) if len(rsi_series_1h) > 0 else 50.0

        # Bollinger 1H
        bb_1h = compute_bollinger_bands(c1h, period=min(20, len(c1h)))
        bb_upper_1h = float(bb_1h["upper"].iloc[-1])
        bb_basis_1h = float(bb_1h["basis"].iloc[-1])
        std_1h = float(bb_1h["std"].iloc[-1])

        open_1h_now = float(o1h.iloc[-1])
        delta = max(0.01 * cur_p, 0.3 * std_1h)

        if bb_upper_1h > cur_p:
            room_to_bb_upper_pct = ((bb_upper_1h - cur_p) / cur_p) * 100.0
        else:
            room_to_bb_upper_pct = 0.0

        # EMA3 y EMA9 de 1H
        ema3_1h = float(c1h.ewm(span=3, adjust=False).mean().iloc[-1])
        ema9_1h = float(c1h.ewm(span=9, adjust=False).mean().iloc[-1])
        ema3_above_ema9 = bool(ema3_1h > ema9_1h)

        # Regla 2.a: Requisito Mínimo Institucional 1H: (EMA3 > EMA9) Y (RSI < 80.0)
        # Excepción Institucional: Reversión Explosiva Día 1 con Gap >= 10%, vela 1H verde y EMA3 1H en fuerte ascenso
        is_day1_reversal = False
        if gap_pct >= 10.0 and len(c1h) >= 2:
            ema3_prev_1h = float(c1h.ewm(span=3, adjust=False).mean().iloc[-2])
            is_day1_reversal = (ema3_1h > ema3_prev_1h and float(c1h.iloc[-1]) >= float(o1h.iloc[-1]))

        # Para standard runners requiere EMA3 > EMA9 y RSI < 80; para Reversión Explosiva Día 1 el impulso inicial es admitido
        meets_1h_req = (ema3_above_ema9 and rsi_1h_val < 80.0) or is_day1_reversal
        has_bb_room = (open_1h_now < (bb_upper_1h - delta)) or (room_to_bb_upper_pct >= 3.0) or ema3_above_ema9 or is_day1_reversal

        macro_1h_ok = meets_1h_req
        res["macro_1h_ok"] = macro_1h_ok
        res["rsi_1h"] = round(rsi_1h_val, 1)
        res["room_to_bb_upper_1h"] = round(room_to_bb_upper_pct, 1)

        if not macro_1h_ok:
            res["reason"] = f"Filtro mínimo 1H no cumplido: Requiere tendencia 1H alcista (EMA3 ${ema3_1h:.2f} > EMA9 ${ema9_1h:.2f}) y RSI < 80 (actual: {rsi_1h_val:.1f})"
            return res
    else:
        # Fallback para IPOs con historial joven en 1H
        macro_1h_ok = True
        res["macro_1h_ok"] = True
        res["rsi_1h"] = 55.0

    # ─────────────────────────────────────────────────────────────
    # PASO 2: Determinar si ya tenemos posición activa y qué tranche toca
    # ─────────────────────────────────────────────────────────────
    reentry_count = int(active_position.get("dca_count") or active_position.get("reentry_count") or 0) if active_position else 0
    is_open_pos = active_position is not None and active_position.get("status") == "open"

    # ─────────────────────────────────────────────────────────────
    # CASO A: TRANCHE 1 (Primer 1/3 - 33.3%)
    # ─────────────────────────────────────────────────────────────
    if not is_open_pos:
        c_prev = float(c5.iloc[-2])
        o_prev = float(o5.iloc[-2])
        l_prev = float(l5.iloc[-2])
        h_prev = float(h5.iloc[-2])

        c_last = float(c5.iloc[-1])
        o_last = float(o5.iloc[-1])
        l_last = float(l5.iloc[-1])
        h_last = float(h5.iloc[-1])

        # Regla 1: Filtro de Confirmación "ORB Breakout" para Gaps Gigantes (> +30%)
        # Si el gap es superior al 30% y la primera vela de 5m fue roja (cierre < apertura):
        # Se prohíbe la compra a ciegas en la apertura de la vela 2 (evita trampas Gap & Crap como STAK/BOLT).
        # Solo se autoriza la entrada si alguna vela posterior rompe por encima del High de la primera vela (ORB High).
        if gap_pct > 30.0 and len(df_5m) >= 2:
            c1_open = float(o5.iloc[0])
            c1_close = float(c5.iloc[0])
            c1_high = float(h5.iloc[0])
            if c1_close < c1_open:
                has_orb_reclaimed = bool(np.any(c5.iloc[1:].to_numpy() >= c1_high * 0.998))
                if not has_orb_reclaimed:
                    res["reason"] = (
                        f"Filtro ORB Gaps > 30%: Vela 1 fue roja de descarga (${c1_open:.2f}->${c1_close:.2f}). "
                        f"Esperando ruptura de ORB High (${c1_high:.2f}). Compra descartada para evitar Gap & Crap."
                    )
                    return res

        # Caso 1: Solo 2 velas de 5m (Ruta Directa inmediata en apertura)
        if len(df_5m) == 2:
            is_candle_1_green = c_prev > o_prev
            if not is_candle_1_green:
                res["reason"] = f"Vela 1 (5m) no es alcista (Close ${c_prev:.2f} <= Open ${o_prev:.2f}). Filtro Anti-Trampa"
                return res

            is_micro_gap_up = o_last >= (c_prev * 0.998)
            is_candle_2_bullish = c_last >= o_last
            if not (is_micro_gap_up and is_candle_2_bullish):
                res["reason"] = f"Vela 2 (5m) no confirma empuje continuo (Open ${o_last:.2f} vs Close_Prev ${c_prev:.2f})"
                return res

            # Regla 3: Stop Loss estructural con Hard Cap de -4.5% máximo
            init_sl = round(max(min(l_prev, cur_p * 0.965), cur_p * 0.955), 2)
            if init_sl <= 0 or init_sl >= cur_p:
                init_sl = round(cur_p * 0.955, 2)

            res.update({
                "should_enter": True,
                "tranche_step": 1,
                "tranche_shares_ratio": 0.3333,
                "rule_code": "GAP_TRANCHE_1",
                "initial_sl": init_sl,
                "reason": (
                    f"Tranche 1/3 activado: Vela 1 verde 5m (${o_prev:.2f}->${c_prev:.2f}), "
                    f"Vela 2 confirmada (${o_last:.2f}), RSI 1H={rsi_1h_val:.1f}, SL=${init_sl:.2f}"
                )
            })
            return res

        # Caso 2: len(df_5m) >= 3 (Evaluar si hubo retroceso/sacudida 'Dip & Rip' o continuación)
        had_red_pullback = bool(np.any(c5.iloc[:-2].to_numpy() <= o5.iloc[:-2].to_numpy()))
        if had_red_pullback:
            # RUTA B: DIP & RIP / GAP FILL & RIP (1..n velas rojas seguidas de 2 velas verdes de giro)
            is_turn_green_1 = c_prev > o_prev
            is_turn_green_2 = (c_last >= o_last) and (c_last >= c_prev)

            if is_turn_green_1 and is_turn_green_2:
                # Mínimo estructural de la sacudida
                low_dip = float(min(float(np.min(l5.iloc[:-2].to_numpy())), l_prev))
                open_day = float(o5.iloc[0])
                est_prev_close = open_day / (1.0 + (gap_pct / 100.0)) if gap_pct > 0 else open_day * 0.95

                # Candado Anti-Desplome con tolerancia de mecha del 3% bajo el cierre previo
                is_gap_fill_sweep = (low_dip <= est_prev_close * 1.01) and (low_dip >= est_prev_close * 0.97)

                if low_dip < (est_prev_close * 0.97):
                    res["reason"] = f"Dip & Rip bloqueado: Low de sacudida (${low_dip:.2f}) perforó cierre previo (${est_prev_close:.2f}) por más del 3%. Caída libre."
                    return res

                if low_dip < est_prev_close and cur_p < est_prev_close:
                    res["reason"] = f"Gap Fill en curso: esperando que el precio recupere el cierre previo (${est_prev_close:.2f}, actual ${cur_p:.2f})"
                    return res

                if not is_gap_fill_sweep:
                    initial_gap_pts = open_day - est_prev_close
                    if initial_gap_pts > 0:
                        max_allowed_drop = open_day - (0.75 * initial_gap_pts)
                        if low_dip < max_allowed_drop:
                            res["reason"] = f"Dip & Rip bloqueado: sacudida borró más del 75% del Gap inicial (Low ${low_dip:.2f} < Piso ${max_allowed_drop:.2f})"
                            return res

                delta = max(0.01 * cur_p, 0.15 * float(h_prev - l_prev))
                # Regla 3: Hard Cap SL en Dip & Rip (-4.5% máximo)
                init_sl = round(max(low_dip - delta, cur_p * 0.955), 2)
                if init_sl <= 0 or init_sl >= cur_p:
                    init_sl = round(cur_p * 0.955, 2)

                rule_label = "GAP_DIP_AND_RIP_1"
                fill_tag = " (Gap Fill)" if is_gap_fill_sweep else ""
                res.update({
                    "should_enter": True,
                    "tranche_step": 1,
                    "tranche_shares_ratio": 0.3333,
                    "rule_code": rule_label,
                    "initial_sl": init_sl,
                    "reason": (
                        f"Dip & Rip Tranche 1 activado{fill_tag}: Sacudida absorbida (Low ${low_dip:.2f}), "
                        f"2 velas verdes de giro (${c_prev:.2f}->${c_last:.2f}), RSI 1H={rsi_1h_val:.1f}, SL=${init_sl:.2f}"
                    )
                })
                return res

        # ─────────────────────────────────────────────────────────────
        # ESTRATEGIA 2: OPENING RANGE BREAKOUT (ORB 15m)
        # ─────────────────────────────────────────────────────────────
        if len(df_5m) >= 4:
            # Los primeros 15 minutos (velas 0, 1, 2) definen el rango de apertura
            h15_range = float(np.max(h5.iloc[:3].to_numpy()))
            l15_range = float(np.min(l5.iloc[:3].to_numpy()))

            is_orb_break = (cur_p > h15_range) and (c_last > o_last)
            v_now = float(v5.iloc[-1])
            v_avg_open = float(np.mean(v5.iloc[:3].to_numpy())) if len(v5) >= 3 else 10000.0
            is_orb_vol = (v_now >= 15000) and (v_now >= v_avg_open * 1.20)

            if is_orb_break and is_orb_vol:
                init_sl = round(min(l15_range, cur_p * 0.96), 2)
                if init_sl <= 0 or init_sl >= cur_p:
                    init_sl = round(cur_p * 0.96, 2)

                res.update({
                    "should_enter": True,
                    "tranche_step": 1,
                    "tranche_shares_ratio": 0.3333,
                    "rule_code": "GAP_ORB_BREAKOUT_1",
                    "initial_sl": init_sl,
                    "reason": (
                        f"ORB 15m Breakout activado: Superó techo de apertura (${h15_range:.2f}), "
                        f"Vela verde (${o_last:.2f}->${c_last:.2f}), Vol={int(v_now)}, SL=${init_sl:.2f}"
                    )
                })
                return res

        # ─────────────────────────────────────────────────────────────
        # ESTRATEGIA 3: VWAP BOUNCE & RELOAD (10:00 - 11:30 ET)
        # ─────────────────────────────────────────────────────────────
        if len(df_5m) >= 6:
            vwap_series = compute_vwap(df_5m)
            cur_vwap = float(vwap_series.iloc[-1]) if len(vwap_series) > 0 else 0.0

            if cur_vwap > 0 and cur_p >= cur_vwap:
                recent_lows = l5.iloc[-3:].to_numpy()
                tested_vwap = bool(np.any((recent_lows <= cur_vwap * 1.015) & (recent_lows >= cur_vwap * 0.980)))
                is_vwap_bounce = tested_vwap and (c_last > o_last) and (c_last >= cur_vwap)

                if is_vwap_bounce:
                    test_low = float(np.min(recent_lows))
                    delta_v = max(0.01 * cur_p, 0.15 * float(h_last - l_last))
                    init_sl = round(test_low - delta_v, 2)
                    if init_sl <= 0 or init_sl >= cur_p:
                        init_sl = round(cur_vwap * 0.985, 2)

                    res.update({
                        "should_enter": True,
                        "tranche_step": 1,
                        "tranche_shares_ratio": 0.3333,
                        "rule_code": "GAP_VWAP_RELOAD_1",
                        "initial_sl": init_sl,
                        "reason": (
                            f"VWAP Reload activado: Testeo en VWAP (${cur_vwap:.2f}) con vela verde de confirmación, "
                            f"SL=${init_sl:.2f}"
                        )
                    })
                    return res

        if not had_red_pullback:
            # Todas las velas previas fueron verdes (Ruta Directa retrasada)
            is_turn_green_1 = c_prev > o_prev
            is_turn_green_2 = (c_last >= o_last) and (c_last >= c_prev or o_last >= c_prev * 0.995)

            if is_turn_green_1 and is_turn_green_2:
                # Regla 3: Hard Cap SL en Ruta Directa retrasada (-4.5% máximo)
                init_sl = round(max(min(l_prev, cur_p * 0.965), cur_p * 0.955), 2)
                if init_sl <= 0 or init_sl >= cur_p:
                    init_sl = round(cur_p * 0.955, 2)

                res.update({
                    "should_enter": True,
                    "tranche_step": 1,
                    "tranche_shares_ratio": 0.3333,
                    "rule_code": "GAP_TRANCHE_1",
                    "initial_sl": init_sl,
                    "reason": (
                        f"Tranche 1/3 activado (Ruta Directa): Vela previa verde 5m (${o_prev:.2f}->${c_prev:.2f}), "
                        f"Vela actual confirmada (${o_last:.2f}), RSI 1H={rsi_1h_val:.1f}, SL=${init_sl:.2f}"
                    )
                })
                return res

        # Si hubo retroceso previo pero no cumplió confirmación de giro
        if had_red_pullback:
            if not is_turn_green_1:
                res["reason"] = f"Dip & Rip en retroceso: vela anterior de 5m sigue roja (${o_prev:.2f}->${c_prev:.2f}). Esperando suelo."
            elif not is_turn_green_2:
                res["reason"] = f"Dip & Rip esperando 2da vela verde de confirmación (Close ${c_last:.2f} vs Prev ${c_prev:.2f})."
            return res

        res["reason"] = f"Vela 5m no confirma empuje continuo (Close ${c_last:.2f} vs Prev ${c_prev:.2f})"
        return res

    # ─────────────────────────────────────────────────────────────
    # CASO B: TRANCHE 2 (Segundo 1/3 - 66.6% acumulado)
    # ─────────────────────────────────────────────────────────────
    elif is_open_pos and reentry_count == 0:
        rebuy_err = _check_15m_rebuy_filters(df_15m, cur_p)
        if rebuy_err:
            res["reason"] = rebuy_err
            return res

        is_15m_continuation = False
        o15_v2 = 0.0
        c15_v1 = 0.0
        if df_15m is not None and len(df_15m) >= 2:
            c15 = _safe_col(df_15m, "close")
            o15 = _safe_col(df_15m, "open")
            c15_v1 = float(c15.iloc[-2])
            o15_v2 = float(o15.iloc[-1])
            is_15m_continuation = o15_v2 >= (c15_v1 * 0.998)

        # Alternativa de Escalamiento HOD Breakout en 5m
        is_hod_breakout = False
        hod_prior = 0.0
        v_now = 0.0
        if df_5m is not None and len(df_5m) >= 3:
            h5_prior = _safe_col(df_5m, "high").iloc[:-1]
            hod_prior = float(h5_prior.max()) if len(h5_prior) > 0 else 0.0
            cur_high_5m = float(_safe_col(df_5m, "high").iloc[-1])
            cur_close_5m = float(_safe_col(df_5m, "close").iloc[-1])
            v5_series = _safe_col(df_5m, "volume")
            v_now = float(v5_series.iloc[-1]) if len(v5_series) > 0 else 0.0
            v_avg = float(v5_series.rolling(10, min_periods=1).mean().iloc[-1]) if len(v5_series) > 0 else 1.0
            is_vol_ok = (v_now >= 10000 and v_now >= v_avg * 1.2) or (v_now >= 25000)
            is_hod_breakout = (cur_high_5m >= hod_prior and cur_close_5m >= (hod_prior * 0.998)) and is_vol_ok

        can_enter_t2 = is_15m_continuation or is_hod_breakout

        if not can_enter_t2:
            res["reason"] = (
                f"Tranche 2 en espera: esperando continuación 15m (Open ${o15_v2:.2f} >= Close ${c15_v1:.2f}) "
                f"o Ruptura HOD en 5m"
            )
            return res

        # Subir SL al precio medio de compra para eliminar riesgo (Breakeven)
        entry_avg = float(active_position.get("avg_price") or cur_p)
        new_sl = round(max(float(active_position.get("stop_loss") or 0.0), entry_avg), 2)
        rule_code_t2 = "GAP_TRANCHE_2" if is_15m_continuation else "GAP_TRANCHE_2_HOD_BREAKOUT"
        t2_reason = (
            f"Tranche 2/3 activado en 15m: Vela 2 Open ${o15_v2:.2f} >= Close ${c15_v1:.2f}. SL Breakeven ${new_sl:.2f}"
            if is_15m_continuation else
            f"Tranche 2/3 activado por HOD Breakout 5m: Máximo ${hod_prior:.2f} superado con volumen ({int(v_now):,}). SL Breakeven ${new_sl:.2f}"
        )

        res.update({
            "should_enter": True,
            "tranche_step": 2,
            "tranche_shares_ratio": 0.3333,
            "rule_code": rule_code_t2,
            "initial_sl": new_sl,
            "reason": t2_reason
        })
        return res

    # ─────────────────────────────────────────────────────────────
    # CASO C: TRANCHE 3 (Tercer 1/3 - Posición Completa 100%)
    # ─────────────────────────────────────────────────────────────
    elif is_open_pos and reentry_count == 1:
        rebuy_err = _check_15m_rebuy_filters(df_15m, cur_p)
        if rebuy_err:
            res["reason"] = rebuy_err
            return res

        is_15m_continuation = False
        low_v2_15m = cur_p * 0.95
        o15_v3 = 0.0
        c15_v2 = 0.0
        if df_15m is not None and len(df_15m) >= 3:
            c15 = _safe_col(df_15m, "close")
            o15 = _safe_col(df_15m, "open")
            l15 = _safe_col(df_15m, "low")
            c15_v2 = float(c15.iloc[-2])
            o15_v3 = float(o15.iloc[-1])
            low_v2_15m = float(l15.iloc[-2])
            is_15m_continuation = o15_v3 >= (c15_v2 * 0.998)

        # Alternativa HOD Breakout en 5m para Tranche 3
        is_hod_breakout = False
        hod_prior = 0.0
        v_now = 0.0
        if df_5m is not None and len(df_5m) >= 4:
            h5_prior = _safe_col(df_5m, "high").iloc[:-1]
            hod_prior = float(h5_prior.max()) if len(h5_prior) > 0 else 0.0
            cur_high_5m = float(_safe_col(df_5m, "high").iloc[-1])
            cur_close_5m = float(_safe_col(df_5m, "close").iloc[-1])
            v5_series = _safe_col(df_5m, "volume")
            v_now = float(v5_series.iloc[-1]) if len(v5_series) > 0 else 0.0
            v_avg = float(v5_series.rolling(10, min_periods=1).mean().iloc[-1]) if len(v5_series) > 0 else 1.0
            is_vol_ok = (v_now >= 10000 and v_now >= v_avg * 1.2) or (v_now >= 25000)
            is_hod_breakout = (cur_high_5m >= hod_prior and cur_close_5m >= (hod_prior * 0.998)) and is_vol_ok

        can_enter_t3 = is_15m_continuation or is_hod_breakout
        is_rsi_acceptable = (rsi_1h_val < 80.0)

        if not can_enter_t3:
            res["reason"] = "Tranche 3 en espera: esperando confirmación de vela 3 en 15m o Ruptura HOD en 5m"
            return res

        if not is_rsi_acceptable:
            res["reason"] = f"Tranche 3 pausado: RSI 1H ({rsi_1h_val:.1f} >= 80.0) en zona extrema"
            return res

        # Subir SL al mínimo de la 2da vela de 15m o soporte de ruptura
        new_sl = round(max(float(active_position.get("stop_loss") or 0.0), low_v2_15m), 2)
        rule_code_t3 = "GAP_TRANCHE_3" if is_15m_continuation else "GAP_TRANCHE_3_HOD_BREAKOUT"
        t3_reason = (
            f"Tranche 3/3 Posición Completa en 15m: Vela 3 confirmada, RSI 1H={rsi_1h_val:.1f}. SL anclado a Low 15m ${new_sl:.2f}"
            if is_15m_continuation else
            f"Tranche 3/3 Posición Completa por HOD Breakout: Máximo superado ${hod_prior:.2f}, RSI 1H={rsi_1h_val:.1f}. SL ${new_sl:.2f}"
        )

        res.update({
            "should_enter": True,
            "tranche_step": 3,
            "tranche_shares_ratio": 0.3334,
            "rule_code": rule_code_t3,
            "initial_sl": new_sl,
            "reason": t3_reason
        })
        return res

    res["reason"] = f"Límite de tranches alcanzado ({reentry_count}/2 recompras completadas)"
    return res


def evaluate_gap_runner_aduana_exit(
    position: Dict[str, Any],
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    df_1d: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Despachador de salidas GAP según el flag GAP_EXIT_MODEL:
      - "LEGACY" (por defecto): comportamiento histórico (_evaluate_gap_runner_legacy_exit).
      - "OPT3": Opción 3 Optimizada (Tramos 25/50/25 + Gracia 10:15 ET), ver gap_exit_opt3.py.
        En OPT3 la lógica LEGACY se evalúa solo en modo sombra (se registra qué habría hecho, sin ejecutarlo).
    """
    from app.stocks.gap_exit_opt3 import is_opt3_gap_position, evaluate_gap_opt3_exit, log_legacy_shadow
    if not is_opt3_gap_position(position):
        return _evaluate_gap_runner_legacy_exit(position, current_price, df_5m, df_15m, df_1h, df_1d)

    opt3_res = evaluate_gap_opt3_exit(position, current_price, df_5m=df_5m, df_15m=df_15m, df_1h=df_1h)
    try:
        legacy_res = _evaluate_gap_runner_legacy_exit(dict(position), current_price, df_5m, df_15m, df_1h, df_1d)
        log_legacy_shadow(position, opt3_res, legacy_res)
    except Exception as e_shadow:
        log_warning(MODULE, f"Error en modo sombra LEGACY para {position.get('ticker')}: {e_shadow}")
    return opt3_res


def _evaluate_gap_runner_legacy_exit(
    position: Dict[str, Any],
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    df_1d: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Reglas de Supervisión, Stop Loss, Trailing Stop y Salidas ADUANA GAP RUNNER:
    
    1. Temporalidad 15 Minutos:
       a) Trailing SL EMA9: Si EMA9[t] > EMA9[t-1] -> Stop Loss debajo de (EMA9[t] - delta).
       b) Primer Cierre Parcial (SELL 50%): En UPPER_6 o RSI_15m > 80.
       c) Excepción de Fuerza Parabólica (Super-Runner Hold):
          Si (Open_15m > BB_Upper_15m) y (SIPV es "BUY") -> HOLD (mantener).
       d) Si no hay datos de UPPER_5/6 -> aplicar según c (RSI > 80 con excepción de Hold).
       e) Clímax Absoluto 1H (Cierre Total 100%): Si RSI_1H > 85 en vela de 1H -> CIERRE TOTAL.
       
    2. Trailing STOP en 1 Hora:
       a) Al terminar vela de 1H:
          Si (High_1H > BB_Upper_1H) y (Close_1H > Open_1H) (vela verde perforando BB Upper):
          Trailing STOP = Open_1H + (Close_1H - Open_1H) / 2.0 (mitad del cuerpo verde).
          
    3. Supervisión Defensiva de Reversión (Parte C):
       - Aplanamiento de ángulo EMA3 1H (slope <= 0.0005) y precio pierde EMA3.
       - Compresión de tamaño de vela 1H sobre BB Upper tras perforación institucional.
    """
    res = {
        "should_exit": False,
        "exit_type": "none",       # 'full', 'partial_50', 'trailing_update'
        "action": "none",          # 'hold', 'sell', etc.
        "rule_code": "",
        "reason": "",
        "shares_to_exit": 0,
        "new_stop_loss": None,
        "ema3_1h": 0.0,
        "ema9_1h": 0.0,
        "ema3_slope_1h": 0.0,
        "range_compression_detected": False,
        "rsi_1h": 50.0,
        "rsi_15m": 50.0
    }

    avg_price = float(position.get("avg_price") or current_price)
    total_shares = int(position.get("shares") or 0)
    cur_sl = float(position.get("stop_loss") or 0.0)

    # ─────────────────────────────────────────────────────────────
    # VALIDACIÓN 0: REGLA 2 - RATCHET A BREAKEVEN (CENTRO DE COSTO + DELTA 1%) AL ALCANZAR +4.0%
    # ─────────────────────────────────────────────────────────────
    highest_p = float(position.get("highest_price_reached") or current_price)
    if current_price > highest_p:
        highest_p = current_price

    gain_peak_pct = ((highest_p - avg_price) / avg_price * 100.0) if avg_price > 0 else 0.0
    if gain_peak_pct >= 4.0:
        be_price = round(avg_price * 1.01, 2)  # Centro de costo + 1.0% de ganancia garantizada
        if cur_sl < be_price:
            cur_sl = be_price
            res["new_stop_loss"] = be_price
            log_info(MODULE, f"🛡️ Ratchet Breakeven activado para {position.get('ticker')}: Pico alcanzado +{gain_peak_pct:.1f}% >= +4%. SL asegurado en ${be_price:.2f} (+1% neto protegido).")

    # ─────────────────────────────────────────────────────────────
    # VALIDACIÓN 0.5: REGLA 5 - TOMA PARCIAL DE BENEFICIOS (50% AL +20.0%)
    # ─────────────────────────────────────────────────────────────
    has_partial_tp = bool(position.get("tp_block1_executed") or position.get("partial_tp_taken") or position.get("partial_taken"))
    cur_gain_pct = ((current_price - avg_price) / avg_price * 100.0) if avg_price > 0 else 0.0
    if total_shares >= 2 and not has_partial_tp and cur_gain_pct >= 20.0:
        shares_to_exit = total_shares // 2
        res.update({
            "should_exit": True,
            "exit_type": "partial_50",
            "rule_code": "ADUANA_GAP_TAKE_PROFIT_20",
            "shares_to_exit": shares_to_exit,
            "reason": f"Toma Parcial 50% al +20%: Ganancia actual alcanzó +{cur_gain_pct:.1f}% >= +20%. Se aseguran {shares_to_exit} acciones en caja."
        })
        return res

    # ─────────────────────────────────────────────────────────────
    # VALIDACIÓN 1: Stop Loss (Hard SL o Breakeven SL Protegido)
    # ─────────────────────────────────────────────────────────────
    if cur_sl > 0 and current_price <= cur_sl:
        is_be_sl = (cur_sl >= avg_price)
        rule_cd = "ADUANA_GAP_BREAKEVEN_SL" if is_be_sl else "ADUANA_GAP_HARD_SL"
        sl_desc = (
            f"Stop Loss Protegido (+1% neto asegurado): Precio (${current_price:.2f}) <= SL (${cur_sl:.2f})"
            if is_be_sl else
            f"Stop Loss ejecutado: Precio (${current_price:.2f}) <= SL (${cur_sl:.2f})"
        )
        res.update({
            "should_exit": True,
            "exit_type": "full",
            "rule_code": rule_cd,
            "shares_to_exit": total_shares,
            "reason": sl_desc
        })
        return res

    # ─────────────────────────────────────────────────────────────
    # PILAR 4: Salida por Invalidación Rápida de Soporte VWAP (-0.4%)
    # ─────────────────────────────────────────────────────────────
    if df_5m is not None and len(df_5m) >= 3:
        vwap_exit_s = compute_vwap(df_5m)
        if len(vwap_exit_s) > 0:
            c_vwap = float(vwap_exit_s.iloc[-1])
            if c_vwap > 0 and current_price < (c_vwap * 0.996):
                res.update({
                    "should_exit": True,
                    "exit_type": "full",
                    "rule_code": "ADUANA_GAP_VWAP_INVALIDATION",
                    "shares_to_exit": total_shares,
                    "reason": f"Invalidación Técnica VWAP: Precio (${current_price:.2f}) perforó soporte de VWAP (${c_vwap:.2f}) por más del 0.4%."
                })
                return res

    # ─────────────────────────────────────────────────────────────
    # SALIDA DEFENSIVA POR ESTANCAMIENTO DE VELOCIDAD 5m (V5m)
    # ─────────────────────────────────────────────────────────────
    if df_5m is not None and len(df_5m) >= 3:
        vel_res = compute_price_velocity_5m(df_5m)
        res["velocity_5m"] = vel_res["v_5m"]
        res["velocity_category"] = vel_res["category"]

        highest_p = float(position.get("highest_price_reached") or current_price)
        is_near_peak = (highest_p > 0) and (current_price >= highest_p * 0.98)
        gap_pos = float(position.get("gap_pct") or 0.0)
        atr_5 = compute_atr(df_5m, 14)
        is_volatile = (gap_pos >= 10.0) or ((atr_5 / max(0.01, current_price)) >= 0.015)

        if vel_res["is_stagnant"] and is_volatile and is_near_peak and total_shares > 0:
            res.update({
                "should_exit": True,
                "exit_type": "full",
                "rule_code": "ADUANA_VELOCITY_STAGNATION_EXIT",
                "shares_to_exit": total_shares,
                "reason": (
                    f"Salida Defensiva por Estancamiento: 3 velas de 5m con velocidad '{vel_res['category']}' "
                    f"({vel_res['v_5m']:+.2f}%) cerca de máximos (${highest_p:.2f}). Se cierra para rotar capital."
                )
            })
            return res

    # ─────────────────────────────────────────────────────────────
    # VALIDACIÓN 2 (Regla 1.e): Clímax Absoluto 1H (RSI_1H > 85 -> CIERRE TOTAL)
    # ─────────────────────────────────────────────────────────────
    c1h = _safe_col(df_1h, "close") if df_1h is not None else pd.Series(dtype=float)
    h1h = _safe_col(df_1h, "high") if df_1h is not None else pd.Series(dtype=float)
    l1h = _safe_col(df_1h, "low") if df_1h is not None else pd.Series(dtype=float)
    o1h = _safe_col(df_1h, "open") if df_1h is not None else pd.Series(dtype=float)

    if len(c1h) >= 4:
        rsi_1h_series = compute_rsi(c1h, period=min(14, len(c1h) - 1))
        rsi_1h_val = float(rsi_1h_series.iloc[-1]) if len(rsi_1h_series) > 0 else 50.0
        res["rsi_1h"] = round(rsi_1h_val, 1)

        if rsi_1h_val > 85.0:
            res.update({
                "should_exit": True,
                "exit_type": "full",
                "rule_code": "ADUANA_GAP_CLIMAX_RSI85",
                "shares_to_exit": total_shares,
                "reason": f"Clímax Parabólico Extremo 1H: RSI_1H={rsi_1h_val:.1f} > 85.0 -> Cierre Total Inmediato (100%)"
            })
            return res

    # ─────────────────────────────────────────────────────────────
    # VALIDACIÓN 3: CÁLCULO PREVIO DE TRAILING STOPS MONOTÓNICOS (Reglas 2.a, 1.a y Ratchet)
    # ─────────────────────────────────────────────────────────────
    best_trail_sl = cur_sl
    best_trail_rule = ""
    best_trail_reason = ""

    # ── Regla 2.a: Trailing STOP en 1 Hora (Midpoint al 50% de Vela Verde sobre BB Upper) ──
    if len(c1h) >= 2:
        bb_1h = compute_bollinger_bands(c1h, period=min(20, len(c1h)))
        for idx in [-2, -1]:
            if abs(idx) <= len(df_1h):
                h_1h_val = float(h1h.iloc[idx])
                o_1h_val = float(o1h.iloc[idx])
                c_1h_val = float(c1h.iloc[idx])
                bb_u_1h_val = float(bb_1h["upper"].iloc[idx])

                # Condición 2.a: High > BB Upper y Close > Open (vela verde)
                if h_1h_val >= bb_u_1h_val and c_1h_val > o_1h_val:
                    midpoint_1h = round(o_1h_val + ((c_1h_val - o_1h_val) / 2.0), 2)
                    if midpoint_1h > best_trail_sl and midpoint_1h < current_price:
                        best_trail_sl = midpoint_1h
                        best_trail_rule = "ADUANA_GAP_TRAIL_MIDPOINT_1H"
                        best_trail_reason = (
                            f"Trailing STOP 1H al 50% de vela verde sobre BB Upper: ${midpoint_1h:.2f} "
                            f"(Open=${o_1h_val:.2f}, Close=${c_1h_val:.2f}, BB_Upper=${bb_u_1h_val:.2f})"
                        )

    # ── Regla 1.a: Trailing STOP en 15m (EMA9 Ascendente -> EMA9 - Delta) ──
    if df_15m is not None and len(df_15m) >= 2:
        c15 = _safe_col(df_15m, "close")
        ema9_15m_series = c15.ewm(span=9, adjust=False).mean()
        ema9_now = float(ema9_15m_series.iloc[-1])
        ema9_prev = float(ema9_15m_series.iloc[-2])

        if ema9_now > ema9_prev:
            atr_15 = compute_atr(df_15m, 14)
            delta = max(0.01 * current_price, 0.5 * atr_15)
            trail_ema9_15m = round(ema9_now - delta, 2)

            if trail_ema9_15m > best_trail_sl and trail_ema9_15m < current_price:
                best_trail_sl = trail_ema9_15m
                best_trail_rule = "ADUANA_GAP_TRAIL_EMA9"
                best_trail_reason = (
                    f"Trailing SL 15m EMA9 ascendente: ${trail_ema9_15m:.2f} "
                    f"(EMA9=${ema9_now:.2f} > Prev=${ema9_prev:.2f}, Delta=${delta:.2f})"
                )

        # ── Trailing Stop Escalonado por Deltas en Lateralidad 15m ──
        h15 = _safe_col(df_15m, "high")
        l15 = _safe_col(df_15m, "low")
        ema3_15_s = c15.ewm(span=3, adjust=False).mean()
        ema3_15_now = float(ema3_15_s.iloc[-1])
        ema3_15_prev = float(ema3_15_s.iloc[-2]) if len(ema3_15_s) >= 2 else ema3_15_now
        slope_ema3_15 = ((ema3_15_now - ema3_15_prev) / max(0.01, ema3_15_prev)) * 100.0
        range_15 = float(h15.iloc[-1]) - float(l15.iloc[-1])
        atr_15_val = compute_atr(df_15m, 14)
        if atr_15_val <= 0:
            atr_15_val = max(0.01, current_price * 0.015)

        price_change_15 = (abs(float(c15.iloc[-1]) - float(c15.iloc[-2])) / float(c15.iloc[-2])) * 100.0 if len(c15) >= 2 else 0.0
        is_lateral_15 = ((abs(slope_ema3_15) <= 0.15) or (price_change_15 <= 0.10)) and (range_15 < 0.50 * atr_15_val)
        if is_lateral_15 and current_price > avg_price:
            delta_gain = max(0.012 * avg_price, 0.50 * atr_15_val)
            highest_seen = float(position.get("highest_price_reached") or current_price)
            steps = max(1, int((highest_seen - avg_price) / delta_gain))
            raw_stepped_sl = avg_price + (steps * delta_gain)
            stepped_sl = round(min(raw_stepped_sl, current_price - (delta_gain * 0.2)), 2)
            if stepped_sl > best_trail_sl and stepped_sl < current_price:
                best_trail_sl = stepped_sl
                best_trail_rule = "ADUANA_GAP_TRAIL_LATERAL_DELTA"
                best_trail_reason = (
                    f"Trailing Escalonado Lateral 15m: SL elevado a Entrada + {steps}*Delta "
                    f"(${stepped_sl:.2f}, Delta=${delta_gain:.2f}, High=${highest_seen:.2f})"
                )

    # ── MEJORA 2: TRAILING STOP ESCALONADO DINÁMICO POR ZONAS DE GANANCIA (TIERED RATCHET) ──
    pnl_pct = ((current_price - avg_price) / avg_price) * 100.0 if avg_price > 0 else 0.0

    # TIER 3: SUPER-RUNNER PARABÓLICO (PnL >= +50.0%)
    if pnl_pct >= 50.0:
        piso_70_pct = avg_price + ((current_price - avg_price) * 0.70)
        candidate_5m = piso_70_pct

        if df_5m is not None and len(df_5m) >= 3:
            c5 = _safe_col(df_5m, "close")
            l5 = _safe_col(df_5m, "low")
            ema3_5m = float(c5.ewm(span=3, adjust=False).mean().iloc[-1])
            low_prev_5m = float(l5.iloc[-2])
            candidate_5m = max(piso_70_pct, min(ema3_5m, low_prev_5m))

        proposed_tier3 = round(candidate_5m, 2)
        if proposed_tier3 > best_trail_sl and proposed_tier3 < current_price:
            best_trail_sl = proposed_tier3
            best_trail_rule = "ADUANA_GAP_TRAIL_TIER3"
            best_trail_reason = (
                f"Trailing Hiper-Protector Tier 3 (+{pnl_pct:.1f}%): Ceñido en ${proposed_tier3:.2f} "
                f"(Blindando 70% de ganancia en 5m)"
            )

    # TIER 2: GANANCIA FUERTE (+25.0% a +49.9%)
    elif pnl_pct >= 25.0:
        piso_15_pct = avg_price * 1.15
        candidate_15m = piso_15_pct

        if df_15m is not None and len(df_15m) >= 2:
            c15 = _safe_col(df_15m, "close")
            l15 = _safe_col(df_15m, "low")
            ema3_15m = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
            low_prev_15m = float(l15.iloc[-2])
            candidate_15m = max(piso_15_pct, min(ema3_15m, low_prev_15m))

        proposed_tier2 = round(candidate_15m, 2)
        if proposed_tier2 > best_trail_sl and proposed_tier2 < current_price:
            best_trail_sl = proposed_tier2
            best_trail_rule = "ADUANA_GAP_TRAIL_TIER2"
            best_trail_reason = (
                f"Trailing Escalonado Tier 2 (+{pnl_pct:.1f}%): Elevado a ${proposed_tier2:.2f} "
                f"(Asegurando piso de +15% / EMA3 15m)"
            )

    # PILAR 3: Escudo Breakeven Automático a +1.0% de ganancia en STOCKS
    if pnl_pct >= 1.0 and best_trail_sl < (avg_price + 0.02):
        proposed_be = round(avg_price + 0.02, 2)
        if proposed_be < current_price:
            best_trail_sl = proposed_be
            best_trail_rule = "ADUANA_GAP_BREAKEVEN_LOCK_1PCT"
            best_trail_reason = f"Escudo Breakeven Lock activado (+{pnl_pct:.2f}% ganancia): SL asegurado en precio de compra + $0.02 (${proposed_be:.2f})"

    # TIER 1 / FALLBACK RATCHET (+7.0% a +24.9% si no se asignó regla previa superior)
    elif pnl_pct >= 7.0 and not best_trail_rule:
        if df_15m is not None and len(df_15m) >= 2:
            l15 = _safe_col(df_15m, "low")
            c15 = _safe_col(df_15m, "close")
            ema3_15m = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
            low_prev_15m = float(l15.iloc[-2])

            proposed_ratchet = round(min(ema3_15m, low_prev_15m), 2)
            if proposed_ratchet > best_trail_sl and proposed_ratchet < current_price:
                best_trail_sl = proposed_ratchet
                best_trail_rule = "ADUANA_GAP_TRAIL_RATCHET_7PCT"
                best_trail_reason = f"Trailing Ratchet 15m elevado a ${proposed_ratchet:.2f} (+{pnl_pct:.1f}% ganancia protegida)"

    # Asignar stop loss si se superó el actual
    if best_trail_sl > cur_sl and best_trail_sl < current_price:
        res["new_stop_loss"] = best_trail_sl
        res["exit_type"] = "trailing_update"
        res["rule_code"] = best_trail_rule
        res["reason"] = best_trail_reason

    # ─────────────────────────────────────────────────────────────
    # VALIDACIÓN 4 (Reglas 1.b, 1.c, 1.d): Salida Parcial SELL 50% en 15m con Excepción HOLD
    # ─────────────────────────────────────────────────────────────
    is_rocket_hold = False
    if df_15m is not None and len(df_15m) >= 2:
        c15 = _safe_col(df_15m, "close")
        o15 = _safe_col(df_15m, "open")
        h15 = _safe_col(df_15m, "high")
        l15 = _safe_col(df_15m, "low")

        # RSI 15m
        rsi_15m_series = compute_rsi(c15, period=min(14, len(c15) - 1))
        rsi_15m_val = float(rsi_15m_series.iloc[-1]) if len(rsi_15m_series) > 0 else 50.0
        res["rsi_15m"] = round(rsi_15m_val, 1)

        # Bandas de Bollinger 15m
        bb_15m = compute_bollinger_bands(c15, period=min(20, len(c15)))
        bb_upper_15m = float(bb_15m["upper"].iloc[-1])
        open_15m_curr = float(o15.iloc[-1])

        # Niveles Fibonacci Bollinger 15m (UPPER_6)
        fib_15m = calculate_fibonacci_bands(df_15m, current_price)
        upper_6 = float(fib_15m.get("upper_6") or 0.0)
        has_upper_data = (upper_6 > 0 and not math.isnan(upper_6))

        # SIPV en 15m
        sipv_is_buy = False
        sipv_pos = str(position.get("sipv_15m") or position.get("sipv_signal_15m") or "").upper()
        if sipv_pos == "BUY":
            sipv_is_buy = True
        elif len(df_15m) >= 2:
            last_c15 = float(c15.iloc[-2])
            last_o15 = float(o15.iloc[-2])
            last_h15 = float(h15.iloc[-2])
            last_l15 = float(l15.iloc[-2])
            rng15 = last_h15 - last_l15
            body15 = last_c15 - last_o15
            if rng15 > 0 and (body15 / rng15) >= 0.30 and body15 > 0:
                sipv_is_buy = True

        is_at_upper_6 = has_upper_data and (current_price >= upper_6)
        is_rsi_over_80 = (rsi_15m_val >= 80.0)
        hit_tp_signal = is_at_upper_6 or is_rsi_over_80

        # Regla 1.c y 1.d: Excepción de Fuerza Parabólica (Super-Runner Hold)
        open_above_bb_15m = (open_15m_curr > bb_upper_15m)
        is_rocket_hold = open_above_bb_15m and sipv_is_buy

        if hit_tp_signal:
            if is_rocket_hold:
                res.update({
                    "action": "hold",
                    "rule_code": "ADUANA_GAP_ROCKET_HOLD",
                    "reason": (
                        f"HOLD Super-Runner: Open 15m (${open_15m_curr:.2f}) > BB Upper (${bb_upper_15m:.2f}) "
                        f"y SIPV es BUY. Manteniendo a pesar de "
                        f"{'UPPER_6 ($' + str(round(upper_6, 2)) + ')' if is_at_upper_6 else ''}"
                        f"{' / ' if is_at_upper_6 and is_rsi_over_80 else ''}"
                        f"{'RSI 15m=' + str(round(rsi_15m_val, 1)) if is_rsi_over_80 else ''}"
                    )
                })
            else:
                # Regla 1.b: Primer cierre parcial SELL 50%
                if not position.get("tp_block1_executed") and total_shares >= 2:
                    exit_shares = max(1, total_shares // 2)
                    res.update({
                        "should_exit": True,
                        "exit_type": "partial_50",
                        "rule_code": "ADUANA_GAP_TP_UPPER6" if is_at_upper_6 else "ADUANA_GAP_TP_RSI80",
                        "shares_to_exit": exit_shares,
                        "reason": (
                            f"Primer Cierre Parcial (SELL 50%): "
                            f"{'Alcanzado UPPER_6 ($' + str(round(upper_6, 2)) + ')' if is_at_upper_6 else ''}"
                            f"{' | ' if is_at_upper_6 and is_rsi_over_80 else ''}"
                            f"{'RSI 15m sobrecomprado (' + str(round(rsi_15m_val, 1)) + ' >= 80)' if is_rsi_over_80 else ''}"
                        )
                    })
                    return res

    # ─────────────────────────────────────────────────────────────
    # VALIDACIÓN 4: Ángulo y Pendiente de EMA3 en 1H (Reglas C.a, C.b, C.c)
    # ─────────────────────────────────────────────────────────────
    if len(c1h) >= 4:
        ema3_1h_series = c1h.ewm(span=3, adjust=False).mean()
        ema9_1h_series = c1h.ewm(span=9, adjust=False).mean()

        ema3_now = float(ema3_1h_series.iloc[-1])
        ema9_now = float(ema9_1h_series.iloc[-1])
        ema3_prev = float(ema3_1h_series.iloc[-2])
        ema3_prev2 = float(ema3_1h_series.iloc[-3])

        slope_now = (ema3_now - ema3_prev) / max(0.01, current_price)
        slope_prev = (ema3_prev - ema3_prev2) / max(0.01, current_price)
        avg_slope = (slope_now + slope_prev) / 2.0

        res["ema3_1h"] = round(ema3_now, 2)
        res["ema9_1h"] = round(ema9_now, 2)
        res["ema3_slope_1h"] = round(avg_slope, 5)

        # Regla C.c: Si la pendiente de EMA3 1H se aplana o cae (slope <= 0.0005) y el precio pierde la EMA3
        if avg_slope <= 0.0005 and current_price < ema3_now:
            is_in_profit = current_price > avg_price
            exit_type = "partial_50" if (is_in_profit and total_shares >= 2) else "full"
            exit_shares = max(1, total_shares // 2) if exit_type == "partial_50" else total_shares

            res.update({
                "should_exit": True,
                "exit_type": exit_type,
                "rule_code": "ADUANA_GAP_EXIT_SLOPE",
                "shares_to_exit": exit_shares,
                "reason": (
                    f"Salida Defensiva ADUANA: Ángulo EMA3 1H aplanado/descendente ({avg_slope:+.5f}) "
                    f"y precio (${current_price:.2f}) bajo EMA3 (${ema3_now:.2f})"
                )
            })
            return res

        # ─────────────────────────────────────────────────────────────
        # VALIDACIÓN 5: Compresión de Rango sobre Bollinger Superior 1H (Regla C.d)
        # ─────────────────────────────────────────────────────────────
        bb_1h = compute_bollinger_bands(c1h, period=min(20, len(c1h)))
        bb_upper_1h = float(bb_1h["upper"].iloc[-1])

        high_now = float(h1h.iloc[-1])
        low_now = float(l1h.iloc[-1])
        high_prev = float(h1h.iloc[-2])
        low_prev = float(l1h.iloc[-2])

        has_pierced_upper = (high_now >= bb_upper_1h) or (high_prev >= bb_upper_1h)

        if has_pierced_upper:
            range_now = high_now - low_now
            range_prev = high_prev - low_prev

            # Si el tamaño de vela (High - Low) empieza a disminuir sensiblemente (< 65% del rango previo)
            if range_prev > 0 and (range_now / range_prev) < 0.65:
                res["range_compression_detected"] = True

                is_in_profit = current_price > avg_price
                exit_type = "partial_50" if (is_in_profit and total_shares >= 2) else "full"
                exit_shares = max(1, total_shares // 2) if exit_type == "partial_50" else total_shares

                new_ratchet_sl = round(max(cur_sl, low_prev), 2)

                res.update({
                    "should_exit": True,
                    "exit_type": exit_type,
                    "rule_code": "ADUANA_GAP_EXIT_COMPRESSION",
                    "shares_to_exit": exit_shares,
                    "new_stop_loss": new_ratchet_sl,
                    "reason": (
                        f"Agotamiento sobre Bollinger 1H: High (${high_now:.2f}) >= BB_Upper (${bb_upper_1h:.2f}). "
                        f"Rango 1H comprimido ({range_now:.2f} < {range_prev:.2f}). Ratchet SL a ${new_ratchet_sl:.2f}"
                    )
                })
                return res

    return res
