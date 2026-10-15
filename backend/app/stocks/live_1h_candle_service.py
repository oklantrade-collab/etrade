"""
eTrade Stocks — Live 1H Forming Candle & SIPV Service
=====================================================
Calcula la vela de 1 HORA EN FORMACIÓN (Live Candle) actualizada en tiempo real cada 5m/15m.
Evalúa:
1. Pendiente de la EMA3 de 1H en tiempo real (Ascendente vs Plana/Descendente).
2. Estructura SIPV (Mecha superior de rechazo vs Mecha inferior de absorción).
3. Candado estricto anti-distribución para compras LONG.
"""

import time
from typing import Dict, Any, Optional
import pandas as pd
import yfinance as yf
from app.core.logger import log_info, log_warning, log_debug

MODULE = "LIVE_1H_CANDLE_SIPV"

# Cache en memoria: { ticker: { "timestamp": float, "data": dict } }
_1H_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 60.0  # 60 segundos de frescura


def get_live_1h_candle_and_sipv(ticker: str, current_price: Optional[float] = None) -> Dict[str, Any]:
    """
    Obtiene la vela de 1H en formación y calcula la pendiente de la EMA3 1H y ratio SIPV.
    """
    clean_ticker = ticker.replace("/", "").replace(".", "").upper().strip()
    now_ts = time.time()

    # 1. Comprobación de Cache rápido
    cached = _1H_CACHE.get(clean_ticker)
    if cached and (now_ts - cached["timestamp"] < CACHE_TTL_SECONDS):
        cached_data = cached["data"]
        # Si vino precio actual, actualizamos pendiente ligera
        if current_price and current_price > 0 and cached_data.get("ema3_1h_prev"):
            prev_ema3 = cached_data["ema3_1h_prev"]
            # EMA3 aproximada con nuevo precio: (current_price * 2/4) + (prev_ema3 * 2/4)
            live_ema3 = (current_price * 0.5) + (prev_ema3 * 0.5)
            slope = live_ema3 - prev_ema3
            cached_data["ema3_1h_live"] = round(live_ema3, 4)
            cached_data["ema3_slope_1h"] = round(slope, 4)
            cached_data["is_ema3_1h_ascending"] = bool(slope > 0.0001)
            cached_data["is_ema3_1h_descending"] = bool(slope <= 0.0001)
            ema9_curr = cached_data.get("ema9_1h", 0.0)
            cached_data["is_ema3_above_ema9"] = bool(live_ema3 > ema9_curr) if ema9_curr > 0 else False
        return cached_data

    fallback_data = {
        "ticker": clean_ticker,
        "is_ema3_1h_ascending": False,
        "is_ema3_1h_descending": True,
        "is_ema3_above_ema9": False,
        "ema3_1h_live": current_price or 0.0,
        "ema3_1h_prev": current_price or 0.0,
        "ema3_slope_1h": 0.0,
        "ema9_1h": current_price or 0.0,
        "candle_open_1h": current_price or 0.0,
        "candle_high_1h": current_price or 0.0,
        "candle_low_1h": current_price or 0.0,
        "candle_close_1h": current_price or 0.0,
        "is_red_candle_1h": False,
        "upper_wick_ratio": 0.0,
        "lower_wick_ratio": 0.0,
        "sipv_upper_rejection": False,
        "sipv_lower_absorption": False,
        "status_reason": "Sin datos 1H históricos",
    }

    try:
        t = yf.Ticker(clean_ticker)
        df_1h = t.history(period="3d", interval="1h")
        if df_1h is None or df_1h.empty or len(df_1h) < 4:
            # Intentar resamplear desde 5m para acciones con pocos datos 1H (ej. IPOs recientes como BRR)
            try:
                df_5m = t.history(period="3d", interval="5m")
                if df_5m is not None and not df_5m.empty and len(df_5m) >= 6:
                    df_resampled = df_5m.resample("1h").agg({
                        "Open": "first",
                        "High": "max",
                        "Low": "min",
                        "Close": "last",
                        "Volume": "sum"
                    }).dropna()
                    if len(df_resampled) >= 2:
                        df_1h = df_resampled
            except Exception as e_resample:
                log_debug(MODULE, f"No se pudo resamplear 5m a 1h para {clean_ticker}: {e_resample}")

        if df_1h is None or df_1h.empty or len(df_1h) < 2:
            _1H_CACHE[clean_ticker] = {"timestamp": now_ts, "data": fallback_data}
            return fallback_data

        # Enriquecer la última vela (en formación) con el precio actual live si se proporcionó
        if current_price and current_price > 0:
            last_idx = df_1h.index[-1]
            df_1h.loc[last_idx, "Close"] = current_price
            if current_price > df_1h.loc[last_idx, "High"]:
                df_1h.loc[last_idx, "High"] = current_price
            if current_price < df_1h.loc[last_idx, "Low"]:
                df_1h.loc[last_idx, "Low"] = current_price

        # Calcular EMAs de 1H
        close_series = df_1h["Close"]
        ema3_series = close_series.ewm(span=3, adjust=False).mean()
        ema9_series = close_series.ewm(span=9, adjust=False).mean()

        ema3_live = float(ema3_series.iloc[-1])
        ema3_prev = float(ema3_series.iloc[-2]) if len(ema3_series) > 1 else ema3_live
        ema9_curr = float(ema9_series.iloc[-1])

        # Pendiente de EMA3 en 1H y relación EMA3 > EMA9
        ema3_slope = ema3_live - ema3_prev
        is_ascending = (ema3_slope > 0.0001)
        is_descending = not is_ascending
        is_ema3_above_ema9 = bool(ema3_live > ema9_curr)

        # Métricas de la vela de 1H en formación (SIPV)
        last_row = df_1h.iloc[-1]
        c_open = float(last_row["Open"])
        c_high = float(last_row["High"])
        c_low = float(last_row["Low"])
        c_close = float(last_row["Close"])

        c_range = max(1e-4, c_high - c_low)
        upper_wick = max(0.0, c_high - max(c_open, c_close))
        lower_wick = max(0.0, min(c_open, c_close) - c_low)

        upper_wick_ratio = upper_wick / c_range
        lower_wick_ratio = lower_wick / c_range
        is_red = (c_close < c_open)

        # Rechazo SIPV superior: mecha arriba >= 40% del rango de 1H
        sipv_upper_rejection = (upper_wick_ratio >= 0.40) or (is_red and upper_wick_ratio >= 0.30)
        # Absorción SIPV inferior: mecha abajo >= 40% y precio recuperando
        sipv_lower_absorption = (lower_wick_ratio >= 0.40) and not is_red

        reason = "Ascendente normal"
        if not is_ema3_above_ema9:
            reason = f"EMA3 1H ({ema3_live:.2f}) <= EMA9 1H ({ema9_curr:.2f}) - Falta cruce alcista"
        elif is_descending:
            reason = f"EMA3 1H cayendo ({ema3_slope:.4f}). Vela 1H en retroceso."
        elif sipv_upper_rejection:
            reason = f"Rechazo SIPV en techo (Mecha sup: {upper_wick_ratio*100:.1f}%)."
        elif sipv_lower_absorption:
            reason = f"Absorción SIPV en soporte (Mecha inf: {lower_wick_ratio*100:.1f}%)."

        result = {
            "ticker": clean_ticker,
            "is_ema3_1h_ascending": is_ascending,
            "is_ema3_1h_descending": is_descending,
            "is_ema3_above_ema9": is_ema3_above_ema9,
            "ema3_1h_live": round(ema3_live, 4),
            "ema3_1h_prev": round(ema3_prev, 4),
            "ema3_slope_1h": round(ema3_slope, 4),
            "ema9_1h": round(ema9_curr, 4),
            "candle_open_1h": round(c_open, 2),
            "candle_high_1h": round(c_high, 2),
            "candle_low_1h": round(c_low, 2),
            "candle_close_1h": round(c_close, 2),
            "is_red_candle_1h": is_red,
            "upper_wick_ratio": round(upper_wick_ratio, 3),
            "lower_wick_ratio": round(lower_wick_ratio, 3),
            "sipv_upper_rejection": sipv_upper_rejection,
            "sipv_lower_absorption": sipv_lower_absorption,
            "status_reason": reason,
        }

        _1H_CACHE[clean_ticker] = {"timestamp": now_ts, "data": result}
        return result

    except Exception as e:
        log_warning(MODULE, f"Error calculando vela 1H live para {clean_ticker}: {e}")
        return fallback_data
