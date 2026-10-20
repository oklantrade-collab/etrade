"""
eTrade v6.0 — ADUANA GAP RUNNER OPTIONS ENGINE
==============================================
Motor institucional para la detección, ranking de velocidad,
selección de contratos en Tranches y supervisión defensiva
de opciones CALLs (Open Gap Up) y PUTs (Open Gap Down).

Pilares del Motor:
1. Umbrales Dinámicos de Gap por Clase de Activo:
   - ETF (SPY, QQQ, IWM): Gap >= 0.60%
   - Mega-Cap (NVDA, TSLA, AAPL, MSFT, AMD, META, AMZN, GOOGL): Gap >= 1.20%
   - High-Beta (COIN, MARA, SMCI, CRWV, PLTR, IREN): Gap >= 3.00%
   - Small/Mid-Cap Opcionable (IRON, CIFR): Gap >= 5.00%
2. Ranking Dinámico de Velocidad (5m) para CALLs y PUTs (%/min).
3. Entradas Escalonadas en Tranches (1/3 o 1/2) con HOD Breakout / LOD Breakdown.
4. Defensivas ADUANA Opciones:
   - SL Dual: Técnico en subyacente (EMA9 15m) + Hard SL en prima (-35%).
   - Stall Guard por Theta Decay (20 min sin avance).
   - Trailing Ratchet por Tiers (Tier 2 al +25%, Tier 3 al +50%).
   - Take Profit Parcial (Upper/Lower 6) y Clímax Total (RSI 1H > 85 / < 15).
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from app.core.logger import log_info, log_warning, log_error
from app.strategy.panic_recovery_gate import calculate_fibonacci_bands

MODULE = "ADUANA_GAP_RUNNER_OPT"

# Clasificación de clases de activos para umbrales dinámicos
ASSET_CLASSES = {
    "ETF": {"SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK", "SMH"},
    "MEGA_CAP": {"NVDA", "TSLA", "AAPL", "MSFT", "AMD", "META", "AMZN", "GOOGL", "GOOG"},
    "HIGH_BETA": {
        "COIN", "MARA", "SMCI", "CRWV", "PLTR", "IREN", "SOFI", "UBER",
        "PYPL", "CRM", "ORCL", "AVGO", "MU", "QCOM", "INTC", "BAC", "JPM", "BABA", "DIS", "XOM"
    }
}

DEFAULT_GAP_THRESHOLDS = {
    "ETF": 0.60,
    "MEGA_CAP": 1.20,
    "HIGH_BETA": 3.00,
    "SMALL_CAP": 5.00
}


def get_asset_class(ticker: str) -> str:
    """Retorna la clase de activo según el ticker."""
    sym = ticker.upper()
    if sym in ASSET_CLASSES["ETF"]:
        return "ETF"
    if sym in ASSET_CLASSES["MEGA_CAP"]:
        return "MEGA_CAP"
    if sym in ASSET_CLASSES["HIGH_BETA"]:
        return "HIGH_BETA"
    return "SMALL_CAP"


def get_min_gap_threshold(ticker: str) -> float:
    """Retorna el umbral mínimo de Gap porcentual requerido para el ticker."""
    ac = get_asset_class(ticker)
    return DEFAULT_GAP_THRESHOLDS.get(ac, 3.00)


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

    for i in range(period, len(series)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    both_zero = (avg_gain == 0.0) & (avg_loss == 0.0)
    rs = avg_gain / avg_loss.replace(0, 1e-6)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(~both_zero, 50.0)
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


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calcula el Average True Range (ATR) de Wilder."""
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


# ══════════════════════════════════════════════════════════════════════════
# REGLA 1: RANKING DINÁMICO DE VELOCIDAD (CALLs y PUTs)
# ══════════════════════════════════════════════════════════════════════════

def calculate_options_velocity_ranking(
    candidates: List[Dict[str, Any]],
    direction: str = "CALL"
) -> List[Dict[str, Any]]:
    """
    Calcula la tasa de aceleración porcentual por minuto (%/min) para CALLs o PUTs.
    - CALL (Gap Up): Mayor tasa positiva por minuto va primero.
    - PUT (Gap Down): Mayor tasa de caída por minuto va primero.
    """
    is_call = direction.upper() in ("CALL", "BULLISH")
    ranked = []

    for item in candidates:
        ticker = item.get("ticker") or item.get("symbol")
        df_5m = item.get("df_5m")

        if df_5m is None or len(df_5m) < 2:
            item_copy = dict(item)
            item_copy["rate_pct_per_min"] = -9999.0
            item_copy["rate_per_min"] = -9999.0
            item_copy["rank_reason"] = "df_5m insuficiente (< 2 velas)"
            ranked.append(item_copy)
            continue

        c5 = _safe_col(df_5m, "close")
        o5 = _safe_col(df_5m, "open")
        c_now = float(c5.iloc[-1])
        c_prev = float(c5.iloc[-2])
        o_now = float(o5.iloc[-1])

        # Base de cálculo: cambio entre las dos últimas velas de 5m
        if is_call:
            diff_price = c_now - c_prev
        else:
            diff_price = c_prev - c_now  # Positivo si el precio cayó

        rate_per_min = diff_price / 5.0
        ref_price = c_prev if c_prev > 0 else (c_now if c_now > 0 else 1.0)
        rate_pct_per_min = (rate_per_min / ref_price) * 100.0

        item_copy = dict(item)
        item_copy["rate_per_min"] = round(rate_per_min, 4)
        item_copy["rate_pct_per_min"] = round(rate_pct_per_min, 4)
        item_copy["direction"] = "CALL" if is_call else "PUT"
        item_copy["c_now_5m"] = c_now
        item_copy["c_prev_5m"] = c_prev
        item_copy["asset_class"] = get_asset_class(ticker)
        item_copy["min_gap_required"] = get_min_gap_threshold(ticker)

        ranked.append(item_copy)

    # Ordenar de forma descendente (mayor tasa va primero)
    ranked.sort(key=lambda x: x.get("rate_pct_per_min", -9999.0), reverse=True)

    for idx, cand in enumerate(ranked):
        cand["velocity_rank"] = idx + 1

    return ranked


# ══════════════════════════════════════════════════════════════════════════
# REGLA 2: EVALUACIÓN DE FILTROS MTF Y TRANCHES (CALLs y PUTs)
# ══════════════════════════════════════════════════════════════════════════

def evaluate_options_gap_entry_tranches(
    ticker: str,
    df_5m: pd.DataFrame,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    gap_pct: float = 0.0,
    active_position: Optional[Dict[str, Any]] = None,
    sipv_signal: Optional[str] = None,
    contract_price: float = 1.0,
    account_budget: float = 1000.0,
    direction: str = "CALL"
) -> Dict[str, Any]:
    """
    Evalúa si un subyacente califica para entrar o escalar en contratos de opciones:
    - CALL (Gap Up): Vela 1 verde, Vela 2 micro-gap alcista, espacio en 1H Bollinger/RSI.
    - PUT (Gap Down): Vela 1 roja, Vela 2 micro-gap bajista, espacio en 1H Bollinger/RSI.
    """
    is_call = direction.upper() in ("CALL", "BULLISH")
    asset_class = get_asset_class(ticker)
    min_gap = get_min_gap_threshold(ticker)

    res: Dict[str, Any] = {
        "should_enter": False,
        "tranche_step": 0,
        "tranche_contracts_ratio": 0.0,
        "rule_code": None,
        "direction": "CALL" if is_call else "PUT",
        "asset_class": asset_class,
        "initial_sl_underlying": None,
        "initial_sl_premium_pct": -35.0,
        "reason": ""
    }

    # 1. Validación de Gap mínimo por clase de activo
    if is_call:
        if gap_pct < min_gap:
            res["reason"] = f"CALL bloqueado: Gap Up +{gap_pct:.2f}% < umbral mínimo requerido ({asset_class}: +{min_gap:.2f}%)"
            return res
    else:
        # En PUTs, el gap debe ser negativo y superar el umbral en valor absoluto
        if gap_pct > -min_gap:
            res["reason"] = f"PUT bloqueado: Gap Down {gap_pct:.2f}% > umbral mínimo requerido ({asset_class}: -{min_gap:.2f}%)"
            return res

    is_open_pos = bool(active_position and str(active_position.get("status", "")).lower() == "open")
    reentry_count = int(active_position.get("reentry_count") or 0) if is_open_pos else 0

    cur_p = float(_safe_col(df_5m, "close").iloc[-1]) if df_5m is not None and not df_5m.empty else 0.0

    # ─────────────────────────────────────────────────────────────
    # CASO A: TRANCHE 1 (Entrada Inicial)
    # ─────────────────────────────────────────────────────────────
    if not is_open_pos:
        # Filtro Macro 1H
        if df_1h is None or len(df_1h) < 15:
            res["reason"] = "Falta historial de 1H para validar filtros macro de Opciones"
            return res

        c1h = _safe_col(df_1h, "close")
        o1h = _safe_col(df_1h, "open")
        h1h = _safe_col(df_1h, "high")
        l1h = _safe_col(df_1h, "low")

        bb_1h = compute_bollinger_bands(c1h, period=20, num_std=2.0)
        rsi_1h_series = compute_rsi(c1h, period=14)

        cur_rsi_1h = float(rsi_1h_series.iloc[-1])
        cur_open_1h = float(o1h.iloc[-1])
        bb_upper_1h = float(bb_1h["upper"].iloc[-1])
        bb_lower_1h = float(bb_1h["lower"].iloc[-1])
        bb_basis_1h = float(bb_1h["basis"].iloc[-1])

        delta_bb = 0.10 * (bb_upper_1h - bb_basis_1h)

        # Reglas 1H para CALL
        if is_call:
            if cur_open_1h >= (bb_upper_1h - delta_bb):
                res["reason"] = f"CALL bloqueado: Open 1H (${cur_open_1h:.2f}) sin espacio ante Banda Superior (${bb_upper_1h:.2f})"
                return res
            if cur_rsi_1h > 60.0:
                res["reason"] = f"CALL bloqueado: RSI 1H ({cur_rsi_1h:.1f}) > 60 (posible agotamiento inicial)"
                return res
        # Reglas 1H para PUT (Espejo)
        else:
            if cur_open_1h <= (bb_lower_1h + delta_bb):
                res["reason"] = f"PUT bloqueado: Open 1H (${cur_open_1h:.2f}) sin espacio ante Banda Inferior (${bb_lower_1h:.2f})"
                return res
            if cur_rsi_1h < 40.0:
                res["reason"] = f"PUT bloqueado: RSI 1H ({cur_rsi_1h:.1f}) < 40 (sobrevendido extremo para entrada inicial)"
                return res

        # Tendencia EMA3 vs EMA9 en 1H o Apertura con Gap sobre EMA9
        ema3_1h = c1h.ewm(span=3, adjust=False).mean()
        ema9_1h = c1h.ewm(span=9, adjust=False).mean()
        cur_ema3 = float(ema3_1h.iloc[-1])
        prev_ema3 = float(ema3_1h.iloc[-2]) if len(ema3_1h) >= 2 else cur_ema3
        cur_ema9 = float(ema9_1h.iloc[-1])

        if is_call:
            is_breakout_ema9 = (cur_open_1h >= cur_ema9)
            is_trend_ok = (cur_ema3 >= cur_ema9) or is_breakout_ema9
            if not is_trend_ok:
                res["reason"] = f"CALL bloqueado: EMA3 1H (${cur_ema3:.2f}) < EMA9 (${cur_ema9:.2f}) y Open (${cur_open_1h:.2f}) < EMA9"
                return res
            if not is_breakout_ema9 and cur_ema3 < prev_ema3:
                res["reason"] = f"CALL bloqueado: Pendiente EMA3 1H no ascendente (${cur_ema3:.2f} < ${prev_ema3:.2f})"
                return res
        else:
            is_breakdown_ema9 = (cur_open_1h <= cur_ema9)
            is_trend_ok = (cur_ema3 <= cur_ema9) or is_breakdown_ema9
            if not is_trend_ok:
                res["reason"] = f"PUT bloqueado: EMA3 1H (${cur_ema3:.2f}) > EMA9 (${cur_ema9:.2f}) y Open (${cur_open_1h:.2f}) > EMA9"
                return res
            if not is_breakdown_ema9 and cur_ema3 > prev_ema3:
                res["reason"] = f"PUT bloqueado: Pendiente EMA3 1H no descendente (${cur_ema3:.2f} > ${prev_ema3:.2f})"
                return res

        # Filtro Micro 5m (Vela 1 y Vela 2)
        if df_5m is None or len(df_5m) < 2:
            res["reason"] = "Esperando al menos 2 velas de 5m post-apertura"
            return res

        c5m = _safe_col(df_5m, "close")
        o5m = _safe_col(df_5m, "open")
        l5m = _safe_col(df_5m, "low")
        h5m = _safe_col(df_5m, "high")

        c1 = float(c5m.iloc[-2])
        o1 = float(o5m.iloc[-2])
        l1 = float(l5m.iloc[-2])
        h1 = float(h5m.iloc[-2])

        c2 = float(c5m.iloc[-1])
        o2 = float(o5m.iloc[-1])

        if is_call:
            # Vela 1 debe ser verde
            if c1 <= o1:
                res["reason"] = f"CALL bloqueado: Vela 1 de 5m fue roja (Close ${c1:.2f} <= Open ${o1:.2f})"
                return res
            # Vela 2: Open >= Close vela anterior
            if o2 < (c1 * 0.998):
                res["reason"] = f"CALL bloqueado: Vela 2 de 5m abrió por debajo del cierre previo (Open ${o2:.2f} < Close ${c1:.2f})"
                return res
            if sipv_signal and str(sipv_signal).upper() not in ("BUY", "STRONG_BUY", "ALCISTA"):
                res["reason"] = f"CALL bloqueado: SIPV indica '{sipv_signal}' en vez de BUY"
                return res

            initial_sl = round(min(l1, o1 * 0.995), 2)
            rule_code = "OPT_GAP_TRANCHE_1_CALL"
            reason_msg = f"CALL Tranche 1 aprobado: Vela 1 verde (+${c1-o1:.2f}), Vela 2 continuación micro-gap (Open ${o2:.2f}), Macro 1H con espacio."

        else:
            # Vela 1 debe ser roja
            if c1 >= o1:
                res["reason"] = f"PUT bloqueado: Vela 1 de 5m fue verde (Close ${c1:.2f} >= Open ${o1:.2f})"
                return res
            # Vela 2: Open <= Close vela anterior
            if o2 > (c1 * 1.002):
                res["reason"] = f"PUT bloqueado: Vela 2 de 5m abrió por encima del cierre previo (Open ${o2:.2f} > Close ${c1:.2f})"
                return res
            if sipv_signal and str(sipv_signal).upper() not in ("SELL", "STRONG_SELL", "BAJISTA"):
                res["reason"] = f"PUT bloqueado: SIPV indica '{sipv_signal}' en vez de SELL"
                return res

            initial_sl = round(max(h1, o1 * 1.005), 2)
            rule_code = "OPT_GAP_TRANCHE_1_PUT"
            reason_msg = f"PUT Tranche 1 aprobado: Vela 1 roja (-${o1-c1:.2f}), Vela 2 continuación bajista (Open ${o2:.2f}), Macro 1H con espacio."

        res.update({
            "should_enter": True,
            "tranche_step": 1,
            "tranche_contracts_ratio": 0.3333,
            "rule_code": rule_code,
            "initial_sl_underlying": initial_sl,
            "reason": reason_msg
        })
        return res

    # ─────────────────────────────────────────────────────────────
    # CASO B: TRANCHE 2 (Segundo Tranche)
    # ─────────────────────────────────────────────────────────────
    elif is_open_pos and reentry_count == 0:
        is_continuation_15m = False
        is_breakout_5m = False
        hod_or_lod = 0.0

        # Verificación en 15m
        if df_15m is not None and len(df_15m) >= 2:
            c15 = _safe_col(df_15m, "close")
            o15 = _safe_col(df_15m, "open")
            c15_v1 = float(c15.iloc[-2])
            o15_v2 = float(o15.iloc[-1])

            if is_call:
                is_continuation_15m = o15_v2 >= (c15_v1 * 0.998)
            else:
                is_continuation_15m = o15_v2 <= (c15_v1 * 1.002)

        # Alternativa en 5m: HOD Breakout (CALL) o LOD Breakdown (PUT)
        if df_5m is not None and len(df_5m) >= 3:
            v5_series = _safe_col(df_5m, "volume")
            v_now = float(v5_series.iloc[-1]) if len(v5_series) > 0 else 0.0
            v_avg = float(v5_series.rolling(10, min_periods=1).mean().iloc[-1]) if len(v5_series) > 0 else 1.0
            is_vol_ok = (v_now >= 5000 and v_now >= v_avg * 1.1) or (v_now >= 15000)

            if is_call:
                h5_prior = _safe_col(df_5m, "high").iloc[:-1]
                hod_or_lod = float(h5_prior.max()) if len(h5_prior) > 0 else 0.0
                cur_high = float(_safe_col(df_5m, "high").iloc[-1])
                is_breakout_5m = (cur_high >= hod_or_lod) and is_vol_ok
            else:
                l5_prior = _safe_col(df_5m, "low").iloc[:-1]
                hod_or_lod = float(l5_prior.min()) if len(l5_prior) > 0 else 0.0
                cur_low = float(_safe_col(df_5m, "low").iloc[-1])
                is_breakout_5m = (cur_low <= hod_or_lod) and is_vol_ok

        can_enter_t2 = is_continuation_15m or is_breakout_5m

        if not can_enter_t2:
            res["reason"] = (
                f"Tranche 2 en espera: sin continuación en 15m ni ruptura de {'HOD' if is_call else 'LOD'} en 5m"
            )
            return res

        # Al entrar en Tranche 2, el SL se ajusta a Breakeven
        entry_avg = float(active_position.get("avg_price") or cur_p)
        new_sl = entry_avg
        rule_code = (
            f"OPT_GAP_TRANCHE_2_{'CALL' if is_call else 'PUT'}"
            if is_continuation_15m else
            f"OPT_GAP_TRANCHE_2_{'HOD' if is_call else 'LOD'}"
        )

        res.update({
            "should_enter": True,
            "tranche_step": 2,
            "tranche_contracts_ratio": 0.3333,
            "rule_code": rule_code,
            "initial_sl_underlying": new_sl,
            "reason": f"Tranche 2 activado ({rule_code}). SL ajustado a Breakeven (${new_sl:.2f})"
        })
        return res

    # ─────────────────────────────────────────────────────────────
    # CASO C: TRANCHE 3 (Tercer Tranche - Posición Completa)
    # ─────────────────────────────────────────────────────────────
    elif is_open_pos and reentry_count == 1:
        # Validación de RSI 1H antes de completar
        if df_1h is not None and len(df_1h) >= 15:
            rsi_1h_series = compute_rsi(_safe_col(df_1h, "close"), period=14)
            cur_rsi_1h = float(rsi_1h_series.iloc[-1])
            if is_call and cur_rsi_1h > 62.0:
                res["reason"] = f"Tranche 3 CALL bloqueado: RSI 1H ({cur_rsi_1h:.1f}) > 62"
                return res
            if not is_call and cur_rsi_1h < 38.0:
                res["reason"] = f"Tranche 3 PUT bloqueado: RSI 1H ({cur_rsi_1h:.1f}) < 38"
                return res

        is_continuation_15m_t3 = False
        if df_15m is not None and len(df_15m) >= 3:
            c15 = _safe_col(df_15m, "close")
            o15 = _safe_col(df_15m, "open")
            c15_v2 = float(c15.iloc[-2])
            o15_v3 = float(o15.iloc[-1])
            if is_call:
                is_continuation_15m_t3 = o15_v3 >= (c15_v2 * 0.998)
            else:
                is_continuation_15m_t3 = o15_v3 <= (c15_v2 * 1.002)

        # Alternativa de ruptura HOD/LOD en 5m
        is_breakout_5m_t3 = False
        if df_5m is not None and len(df_5m) >= 3:
            v5_series = _safe_col(df_5m, "volume")
            v_now = float(v5_series.iloc[-1]) if len(v5_series) > 0 else 0.0
            v_avg = float(v5_series.rolling(10, min_periods=1).mean().iloc[-1]) if len(v5_series) > 0 else 1.0
            is_vol_ok = (v_now >= 5000 and v_now >= v_avg * 1.1) or (v_now >= 15000)

            if is_call:
                h5_prior = _safe_col(df_5m, "high").iloc[:-1]
                hod_prior = float(h5_prior.max()) if len(h5_prior) > 0 else 0.0
                cur_high = float(_safe_col(df_5m, "high").iloc[-1])
                is_breakout_5m_t3 = (cur_high >= hod_prior) and is_vol_ok
            else:
                l5_prior = _safe_col(df_5m, "low").iloc[:-1]
                lod_prior = float(l5_prior.min()) if len(l5_prior) > 0 else 0.0
                cur_low = float(_safe_col(df_5m, "low").iloc[-1])
                is_breakout_5m_t3 = (cur_low <= lod_prior) and is_vol_ok

        can_enter_t3 = is_continuation_15m_t3 or is_breakout_5m_t3

        if not can_enter_t3:
            res["reason"] = f"Tranche 3 en espera: sin confirmación de Vela 3 en 15m ni nueva ruptura"
            return res

        rule_code = f"OPT_GAP_TRANCHE_3_{'CALL' if is_call else 'PUT'}"
        res.update({
            "should_enter": True,
            "tranche_step": 3,
            "tranche_contracts_ratio": 0.3334,
            "rule_code": rule_code,
            "reason": f"Tranche 3/3 final aprobado. Posición de opciones 100% llena ({rule_code})"
        })
        return res

    res["reason"] = f"Tranches ya completados (reentry_count={reentry_count})"
    return res


# ══════════════════════════════════════════════════════════════════════════
# REGLA 3: SUPERVISIÓN DEFENSIVA ADUANA OPCIONES (SALIDAS Y TRAILING)
# ══════════════════════════════════════════════════════════════════════════

def evaluate_options_gap_aduana_exit(
    position: Dict[str, Any],
    current_underlying_price: float,
    current_option_premium: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    position_age_minutes: float = 0.0,
    sipv_signal: Optional[str] = None
) -> Dict[str, Any]:
    """
    Supervisión continua defensiva para posiciones de opciones:
    1. Hard Stop Loss en Prima (-35%).
    2. Stall Guard por Theta Decay (20 min sin avance).
    3. Trailing Ratchet por Tiers (Tier 2 al +25% de prima, Tier 3 al +50%).
    4. Stop Loss Dinámico en Subyacente (EMA9 15m).
    5. Trailing Stop 1H Midpoint (mitad de vela 1H cerrada fuera de Bollinger).
    6. Take Profit Parcial (Upper/Lower 6) & Total Clímax (RSI 1H > 85 / < 15).
    """
    direction = str(position.get("direction", "CALL")).upper()
    is_call = direction in ("CALL", "BULLISH")

    res: Dict[str, Any] = {
        "should_exit": False,
        "exit_type": None,          # 'hard_stop', 'stall_guard', 'trailing_stop', 'take_profit_partial', 'climax_total'
        "contracts_ratio_to_exit": 0.0,
        "rule_code": None,
        "new_stop_loss_underlying": None,
        "reason": ""
    }

    entry_premium = float(position.get("avg_price") or position.get("entry_debit") or current_option_premium)
    if entry_premium <= 0.0:
        entry_premium = current_option_premium

    unrealized_pnl_pct = ((current_option_premium - entry_premium) / entry_premium) * 100.0 if entry_premium > 0 else 0.0
    highest_premium_seen = float(position.get("highest_premium_seen") or max(entry_premium, current_option_premium))

    # 1. HARD STOP LOSS EN PRIMA (-35%)
    if unrealized_pnl_pct <= -35.0:
        res.update({
            "should_exit": True,
            "exit_type": "hard_stop",
            "contracts_ratio_to_exit": 1.0,
            "rule_code": "OPT_GAP_HARD_SL_PREM",
            "reason": f"Hard SL activado: Prima cae {unrealized_pnl_pct:.1f}% <= -35.0% (${current_option_premium:.2f} vs compra ${entry_premium:.2f})"
        })
        return res

    # 2. STALL GUARD POR THETA DECAY (20 min estancado)
    reentry_count = int(position.get("reentry_count") or 0)
    if position_age_minutes >= 20.0 and reentry_count == 0 and unrealized_pnl_pct <= -15.0:
        res.update({
            "should_exit": True,
            "exit_type": "stall_guard",
            "contracts_ratio_to_exit": 1.0,
            "rule_code": "OPT_GAP_STALL_GUARD",
            "reason": f"Stall Guard activado: {position_age_minutes:.0f}m sin avance y prima cae {unrealized_pnl_pct:.1f}%. Cierre defensivo ante Theta."
        })
        return res

    # 3. TRAILING RATCHET POR TIERS DE GANANCIA EN PRIMA
    # Tier 3 (Super Runner >= +50% PnL de prima): blindar al menos el 70% del beneficio pico
    peak_pnl_pct = ((highest_premium_seen - entry_premium) / entry_premium) * 100.0 if entry_premium > 0 else 0.0
    if peak_pnl_pct >= 50.0:
        guaranteed_pnl_pct = peak_pnl_pct * 0.70
        guaranteed_premium = entry_premium * (1.0 + guaranteed_pnl_pct / 100.0)

        if current_option_premium <= guaranteed_premium:
            res.update({
                "should_exit": True,
                "exit_type": "trailing_stop",
                "contracts_ratio_to_exit": 1.0,
                "rule_code": "OPT_GAP_TRAIL_TIER3",
                "reason": f"Tier 3 Ratchet activado: Prima (${current_option_premium:.2f}) perfora blindaje del 70% pico (${guaranteed_premium:.2f}, +{guaranteed_pnl_pct:.1f}% neto)"
            })
            return res

    # Tier 2 (Runner >= +25% PnL de prima): piso garantizado de al menos +15% neto
    elif peak_pnl_pct >= 25.0:
        guaranteed_premium = entry_premium * 1.15
        if current_option_premium <= guaranteed_premium:
            res.update({
                "should_exit": True,
                "exit_type": "trailing_stop",
                "contracts_ratio_to_exit": 1.0,
                "rule_code": "OPT_GAP_TRAIL_TIER2",
                "reason": f"Tier 2 Ratchet activado: Prima (${current_option_premium:.2f}) perfora piso garantizado de +15% (${guaranteed_premium:.2f})"
            })
            return res

    # 4. CLÍMAX TOTAL RSI 1H (> 85 en CALLs / < 15 en PUTs)
    if df_1h is not None and len(df_1h) >= 15:
        rsi_1h = float(compute_rsi(_safe_col(df_1h, "close"), period=14).iloc[-1])
        if is_call and rsi_1h >= 85.0:
            res.update({
                "should_exit": True,
                "exit_type": "climax_total",
                "contracts_ratio_to_exit": 1.0,
                "rule_code": "OPT_GAP_TP_CLIMAX",
                "reason": f"Take Profit Clímax Total: RSI 1H ({rsi_1h:.1f}) >= 85.0 en subyacente. Liquidación 100% de CALLs."
            })
            return res
        elif not is_call and rsi_1h <= 15.0:
            res.update({
                "should_exit": True,
                "exit_type": "climax_total",
                "contracts_ratio_to_exit": 1.0,
                "rule_code": "OPT_GAP_TP_CLIMAX",
                "reason": f"Take Profit Clímax Total: RSI 1H ({rsi_1h:.1f}) <= 15.0 en subyacente. Liquidación 100% de PUTs."
            })
            return res

    # 5. TAKE PROFIT PARCIAL (50% de contratos en Upper/Lower 6 o RSI 5m Extremo)
    tp_block1 = bool(position.get("tp_block1_executed", False))
    if not tp_block1 and df_5m is not None and len(df_5m) >= 15:
        c5 = _safe_col(df_5m, "close")
        rsi_5m = float(compute_rsi(c5, period=14).iloc[-1])
        c_now = float(c5.iloc[-1])
        o_now = float(_safe_col(df_5m, "open").iloc[-1])

        # Excepción Rocket Hold: vela abre fuera de Bollinger y SIPV acompaña con fuerza
        bb_5m = compute_bollinger_bands(c5, period=20, num_std=2.0)
        upper_bb = float(bb_5m["upper"].iloc[-1])
        lower_bb = float(bb_5m["lower"].iloc[-1])

        if is_call:
            is_rocket = (o_now > upper_bb) and (str(sipv_signal).upper() in ("BUY", "STRONG_BUY"))
            if not is_rocket and rsi_5m >= 80.0:
                res.update({
                    "should_exit": True,
                    "exit_type": "take_profit_partial",
                    "contracts_ratio_to_exit": 0.50,
                    "rule_code": "OPT_GAP_TP_UPPER6_PARTIAL",
                    "reason": f"TP Parcial 50% contratos: Subyacente en zona extrema RSI 5m ({rsi_5m:.1f} >= 80.0)."
                })
                return res
        else:
            is_rocket_drop = (o_now < lower_bb) and (str(sipv_signal).upper() in ("SELL", "STRONG_SELL"))
            if not is_rocket_drop and rsi_5m <= 20.0:
                res.update({
                    "should_exit": True,
                    "exit_type": "take_profit_partial",
                    "contracts_ratio_to_exit": 0.50,
                    "rule_code": "OPT_GAP_TP_LOWER6_PARTIAL",
                    "reason": f"TP Parcial 50% contratos: Subyacente en zona de soporte extremo RSI 5m ({rsi_5m:.1f} <= 20.0)."
                })
                return res

    # 6. STOP LOSS TÉCNICO EN SUBYACENTE (EMA9 15m)
    current_sl = float(position.get("stop_loss_underlying") or 0.0)
    if df_15m is not None and len(df_15m) >= 10:
        c15 = _safe_col(df_15m, "close")
        ema9_15m = c15.ewm(span=9, adjust=False).mean()
        cur_ema9_15m = float(ema9_15m.iloc[-1])
        prev_ema9_15m = float(ema9_15m.iloc[-2]) if len(ema9_15m) >= 2 else cur_ema9_15m
        delta_sl = 0.002 * cur_ema9_15m

        if is_call:
            # Si EMA9 sube, elevar SL dinámico
            if cur_ema9_15m > prev_ema9_15m:
                proposed_sl = round(cur_ema9_15m - delta_sl, 2)
                if proposed_sl > current_sl:
                    res["new_stop_loss_underlying"] = proposed_sl
                    res["rule_code"] = "OPT_GAP_SL_EMA9_15M"
            # Si el precio perfora el SL actual
            if current_sl > 0.0 and current_underlying_price <= current_sl:
                res.update({
                    "should_exit": True,
                    "exit_type": "stop_loss_underlying",
                    "contracts_ratio_to_exit": 1.0,
                    "rule_code": "OPT_GAP_SL_EMA9_15M",
                    "reason": f"SL Técnico perforado: Subyacente (${current_underlying_price:.2f}) <= SL (${current_sl:.2f})"
                })
                return res
        else:
            # En PUTs, el SL del subyacente es un techo. Si EMA9 baja, reducir techo
            if cur_ema9_15m < prev_ema9_15m:
                proposed_sl = round(cur_ema9_15m + delta_sl, 2)
                if current_sl == 0.0 or proposed_sl < current_sl:
                    res["new_stop_loss_underlying"] = proposed_sl
                    res["rule_code"] = "OPT_GAP_SL_EMA9_15M"
            if current_sl > 0.0 and current_underlying_price >= current_sl:
                res.update({
                    "should_exit": True,
                    "exit_type": "stop_loss_underlying",
                    "contracts_ratio_to_exit": 1.0,
                    "rule_code": "OPT_GAP_SL_EMA9_15M",
                    "reason": f"SL Técnico perforado: Subyacente (${current_underlying_price:.2f}) >= SL (${current_sl:.2f})"
                })
                return res

    return res
