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

MODULE = "ADUANA_GAP_RUNNER"


def _safe_col(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Retorna la serie de la columna en minúscula o mayúscula de forma segura."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    if col_name in df.columns:
        return df[col_name].astype(float)
    cap = col_name.capitalize()
    if cap in df.columns:
        return df[cap].astype(float)
    upper = col_name.upper()
    if upper in df.columns:
        return df[upper].astype(float)
    return pd.Series(dtype=float)


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
         - RSI_1H <= 70.0 (umbral calibrado para no asfixiar runners de apertura).
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

        # Regla 2.a: Open_1H < (Banda Superior - Delta) y RSI 1H <= 70.0
        # (Se calibra RSI <= 70.0 en lugar de 60 para evitar vetar runners reales con gap fuerte)
        has_bb_room = (open_1h_now < (bb_upper_1h - delta)) or (room_to_bb_upper_pct >= 3.0)
        has_healthy_rsi = (rsi_1h_val <= 70.0)

        macro_1h_ok = has_bb_room and has_healthy_rsi
        res["macro_1h_ok"] = macro_1h_ok
        res["rsi_1h"] = round(rsi_1h_val, 1)
        res["room_to_bb_upper_1h"] = round(room_to_bb_upper_pct, 1)

        if not macro_1h_ok:
            if not has_bb_room:
                res["reason"] = f"Macro 1H sin espacio a BB Superior (Open=${open_1h_now:.2f} >= BB_Upper=${bb_upper_1h:.2f} - Delta=${delta:.2f})"
                return res
            if not has_healthy_rsi:
                res["reason"] = f"RSI 1H sobrecomprado ({rsi_1h_val:.1f} > 70.0). Riesgo de clímax extremo"
                return res
    else:
        # Fallback para IPOs con historial joven en 1H
        macro_1h_ok = True
        res["macro_1h_ok"] = True
        res["rsi_1h"] = 55.0

    # ─────────────────────────────────────────────────────────────
    # PASO 2: Determinar si ya tenemos posición activa y qué tranche toca
    # ─────────────────────────────────────────────────────────────
    reentry_count = int(active_position.get("reentry_count") or 0) if active_position else 0
    is_open_pos = active_position is not None and active_position.get("status") == "open"

    # ─────────────────────────────────────────────────────────────
    # CASO A: TRANCHE 1 (Primer 1/3 - 33.3%)
    # ─────────────────────────────────────────────────────────────
    if not is_open_pos:
        # 2.b: Vela 1 (5m) debe ser VERDE (Close > Open)
        c_v1 = float(c5.iloc[-2])
        o_v1 = float(o5.iloc[-2])
        is_candle_1_green = c_v1 > o_v1

        if not is_candle_1_green:
            res["reason"] = f"Vela 1 (5m) no es alcista (Close ${c_v1:.2f} <= Open ${o_v1:.2f}). Filtro Anti-Trampa"
            return res

        # 2.c: Vela 2 (5m): Open > Close de la vela anterior (micro-gap) o continuación fuerte
        o_v2 = float(o5.iloc[-1])
        c_v2 = float(c5.iloc[-1])
        is_micro_gap_up = o_v2 >= (c_v1 * 0.998)  # Tolerancia mínima 0.2%
        is_candle_2_bullish = c_v2 >= o_v2

        if not (is_micro_gap_up and is_candle_2_bullish):
            res["reason"] = f"Vela 2 (5m) no confirma empuje continuo (Open ${o_v2:.2f} vs Close_Prev ${c_v1:.2f})"
            return res

        # Cálculo de Stop Loss inicial: Low de la vela 1 de 5m
        low_v1 = float(l5.iloc[-2])
        init_sl = round(min(low_v1, cur_p * 0.95), 2)
        if init_sl <= 0 or init_sl >= cur_p:
            init_sl = round(cur_p * 0.95, 2)

        res.update({
            "should_enter": True,
            "tranche_step": 1,
            "tranche_shares_ratio": 0.3333,
            "rule_code": "GAP_TRANCHE_1",
            "initial_sl": init_sl,
            "reason": (
                f"Tranche 1/3 activado: Vela 1 verde 5m (${o_v1:.2f}->${c_v1:.2f}), "
                f"Vela 2 confirmada (${o_v2:.2f}), RSI 1H={rsi_1h_val:.1f}, SL=${init_sl:.2f}"
            )
        })
        return res

    # ─────────────────────────────────────────────────────────────
    # CASO B: TRANCHE 2 (Segundo 1/3 - 66.6% acumulado)
    # ─────────────────────────────────────────────────────────────
    elif is_open_pos and reentry_count == 0:
        if df_15m is None or len(df_15m) < 2:
            res["reason"] = "Esperando formación de 2da vela de 15m para Tranche 2"
            return res

        c15 = _safe_col(df_15m, "close")
        o15 = _safe_col(df_15m, "open")

        c15_v1 = float(c15.iloc[-2])
        o15_v2 = float(o15.iloc[-1])

        # En 15m: Open 2da vela > Close vela 1 (continuación alcista en 15m)
        is_15m_continuation = o15_v2 >= (c15_v1 * 0.998)

        if not is_15m_continuation:
            res["reason"] = f"15m Vela 2 sin continuación (Open ${o15_v2:.2f} < Close_Prev ${c15_v1:.2f})"
            return res

        # Subir SL al precio medio de compra para eliminar riesgo (Breakeven)
        entry_avg = float(active_position.get("avg_price") or cur_p)
        new_sl = round(max(float(active_position.get("stop_loss") or 0.0), entry_avg), 2)

        res.update({
            "should_enter": True,
            "tranche_step": 2,
            "tranche_shares_ratio": 0.3333,
            "rule_code": "GAP_TRANCHE_2",
            "initial_sl": new_sl,
            "reason": (
                f"Tranche 2/3 activado en 15m: Vela 2 Open ${o15_v2:.2f} >= Close ${c15_v1:.2f}. "
                f"SL ajustado a Breakeven ${new_sl:.2f}"
            )
        })
        return res

    # ─────────────────────────────────────────────────────────────
    # CASO C: TRANCHE 3 (Tercer 1/3 - Posición Completa 100%)
    # ─────────────────────────────────────────────────────────────
    elif is_open_pos and reentry_count == 1:
        if df_15m is None or len(df_15m) < 3:
            res["reason"] = "Esperando formación de 3ra vela de 15m para Tranche 3"
            return res

        c15 = _safe_col(df_15m, "close")
        o15 = _safe_col(df_15m, "open")
        l15 = _safe_col(df_15m, "low")

        c15_v2 = float(c15.iloc[-2])
        o15_v3 = float(o15.iloc[-1])

        is_15m_continuation = o15_v3 >= (c15_v2 * 0.998)
        # Filtro de sobrecompra: RSI 1H <= 72.0
        is_rsi_acceptable = (rsi_1h_val <= 72.0)

        if not is_15m_continuation:
            res["reason"] = f"15m Vela 3 sin continuación (Open ${o15_v3:.2f} < Close_Prev ${c15_v2:.2f})"
            return res

        if not is_rsi_acceptable:
            res["reason"] = f"Tranche 3 pausado: RSI 1H ({rsi_1h_val:.1f} > 72.0) en zona extrema"
            return res

        # Subir SL al mínimo de la 2da vela de 15m
        low_v2_15m = float(l15.iloc[-2])
        new_sl = round(max(float(active_position.get("stop_loss") or 0.0), low_v2_15m), 2)

        res.update({
            "should_enter": True,
            "tranche_step": 3,
            "tranche_shares_ratio": 0.3334,
            "rule_code": "GAP_TRANCHE_3",
            "initial_sl": new_sl,
            "reason": (
                f"Tranche 3/3 Posición Completa: Vela 3 15m confirmada, RSI 1H={rsi_1h_val:.1f}. "
                f"SL anclado a Low 15m ${new_sl:.2f}"
            )
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
    Reglas de Supervisión y Salida ADUANA (Parte C):
    a) EMA3 > EMA9 en 1H o 1D (Tendencia base).
    b) EMA3 en 1H debe estar en modo ascendente (slope > 0).
    c) Mínimo ángulo permitido EMA3: si se acerca a lateral o caída (slope <= 0.0005) -> Salida defensiva.
    d) Tamaño de vela (High - Low) en 1H empieza a disminuir a partir de la vela cuyo High > BB Upper 1H.
       Agotamiento institucional -> Toma de beneficios TP 50% y trailing ratchet al Low anterior.
    """
    res = {
        "should_exit": False,
        "exit_type": "none",       # 'full', 'partial_50', 'trailing_update'
        "rule_code": "",
        "reason": "",
        "shares_to_exit": 0,
        "new_stop_loss": None,
        "ema3_1h": 0.0,
        "ema9_1h": 0.0,
        "ema3_slope_1h": 0.0,
        "range_compression_detected": False
    }

    avg_price = float(position.get("avg_price") or current_price)
    total_shares = int(position.get("shares") or 0)
    cur_sl = float(position.get("stop_loss") or 0.0)

    # ─────────────────────────────────────────────────────────────
    # VALIDACIÓN 1: Hard Stop Loss
    # ─────────────────────────────────────────────────────────────
    if cur_sl > 0 and current_price <= cur_sl:
        res.update({
            "should_exit": True,
            "exit_type": "full",
            "rule_code": "ADUANA_GAP_HARD_SL",
            "shares_to_exit": total_shares,
            "reason": f"Stop Loss ejecutado: Precio (${current_price:.2f}) <= SL (${cur_sl:.2f})"
        })
        return res

    # ─────────────────────────────────────────────────────────────
    # VALIDACIÓN 2: Ángulo y Pendiente de EMA3 en 1H (Reglas C.a, C.b, C.c)
    # ─────────────────────────────────────────────────────────────
    if df_1h is not None and len(df_1h) >= 4:
        c1h = _safe_col(df_1h, "close")
        h1h = _safe_col(df_1h, "high")
        l1h = _safe_col(df_1h, "low")

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
            # Salida defensiva: si está en ganancia, liquidar 50% para proteger; si está en pérdida, salida total.
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
        # VALIDACIÓN 3: Compresión de Rango sobre Bollinger Superior 1H (Regla C.d)
        # ─────────────────────────────────────────────────────────────
        bb_1h = compute_bollinger_bands(c1h, period=min(20, len(c1h)))
        bb_upper_1h = float(bb_1h["upper"].iloc[-1])

        # Revisar si la vela actual o anterior perforó la banda superior (High > BB Upper)
        high_now = float(h1h.iloc[-1])
        low_now = float(l1h.iloc[-1])
        high_prev = float(h1h.iloc[-2])
        low_prev = float(l1h.iloc[-2])

        has_pierced_upper = (high_now >= bb_upper_1h) or (high_prev >= bb_upper_1h)

        if has_pierced_upper:
            range_now = high_now - low_now
            range_prev = high_prev - low_prev

            # Si el tamaño de vela (High - Low) empieza a disminuir sensiblemente (compresión < 65% del rango previo)
            if range_prev > 0 and (range_now / range_prev) < 0.65:
                res["range_compression_detected"] = True
                
                # Salida por agotamiento institucional en techo
                is_in_profit = current_price > avg_price
                exit_type = "partial_50" if (is_in_profit and total_shares >= 2) else "full"
                exit_shares = max(1, total_shares // 2) if exit_type == "partial_50" else total_shares
                
                # Trailing Ratchet: elevar SL al mínimo de la vela de 1H previa
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

    # ─────────────────────────────────────────────────────────────
    # VALIDACIÓN 4: Trailing Ratchet Acelerado en 15m (Proteger Ganancia > +7%)
    # ─────────────────────────────────────────────────────────────
    pnl_pct = ((current_price - avg_price) / avg_price) * 100.0 if avg_price > 0 else 0.0

    if pnl_pct >= 7.0 and df_15m is not None and len(df_15m) >= 2:
        l15 = _safe_col(df_15m, "low")
        c15 = _safe_col(df_15m, "close")
        ema3_15m = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
        low_prev_15m = float(l15.iloc[-2])

        proposed_sl = round(max(cur_sl, min(ema3_15m, low_prev_15m)), 2)
        if proposed_sl > cur_sl and proposed_sl < current_price:
            res.update({
                "should_exit": False,
                "exit_type": "trailing_update",
                "new_stop_loss": proposed_sl,
                "reason": f"Trailing Ratchet 15m elevado a ${proposed_sl:.2f} (+{pnl_pct:.1f}% ganancia protegida)"
            })
            return res

    return res
