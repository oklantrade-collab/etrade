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


# ─────────────────────────────────────────────────────────────────────────────
# ADUANA OPCIONES: Daily Runway 1D (con excepción por volumen), anti-agotamiento
# RSI multi-timeframe y alineación tendencial EMA3/EMA9 en 1H (CALLs y PUTs).
# ─────────────────────────────────────────────────────────────────────────────

# Runway mínimo (%) del Open diario hacia la banda de Bollinger 1D de la dirección
# (BB_UPPER para CALLs / BB_LOWER para PUTs). Los ETFs tienen un rango diario natural
# mucho menor; toda acción individual exige 20%.
OPT_RUNWAY_MIN_PCT_BY_CLASS = {"ETF": 2.5}
OPT_RUNWAY_MIN_PCT_DEFAULT = 20.0

# Excepción por volumen masivo: bajo el umbral sólo entra con RVOL >= 3.0x y presión
# unidireccional; el volumen proyecta una expansión de banda de 3.5 pp por cada 1.0x
# de RVOL sobre 1.0x (tope 25 pp).
OPT_RUNWAY_MASSIVE_RVOL = 3.0
OPT_RUNWAY_DELTA_PP_PER_RVOL = 3.5
OPT_RUNWAY_MAX_DELTA_PP = 25.0

# Anti-agotamiento RSI: techos para CALLs, pisos para PUTs.
OPT_RSI_LIMITS = {
    "CALL": {"5m": 72.0, "15m": 75.0, "1h": 75.0},
    "PUT": {"5m": 28.0, "15m": 30.0, "1h": 40.0},
}


def get_options_runway_threshold(ticker: str) -> float:
    """Runway mínimo (%) exigido al subyacente según su clase de activo."""
    return OPT_RUNWAY_MIN_PCT_BY_CLASS.get(get_asset_class(ticker), OPT_RUNWAY_MIN_PCT_DEFAULT)


def evaluate_options_daily_runway(
    ticker: str,
    direction: str,
    open_price: float,
    bb_upper_1d: float,
    bb_lower_1d: float,
    rvol: float = 1.0,
    pressure_ok: bool = True,
) -> Dict[str, Any]:
    """
    Evalúa el espacio diario disponible antes de chocar con la banda de Bollinger 1D.

    Base_Runway:
        CALL = (BB_UPPER_1D - Open) / Open * 100
        PUT  = (Open - BB_LOWER_1D) / Open * 100

    - Base_Runway >= umbral (20% acciones / 2.5% ETFs) -> aprobado (modo BASE).
    - Base_Runway <  umbral -> EXCLUIDO, salvo ignición por volumen masivo
      (RVOL >= 3.0x y presión unidireccional), caso en que se proyecta:
        Runway_Proyectado = Base_Runway + min(25, 3.5 * (RVOL - 1.0))
      y debe alcanzar el umbral (modo VOLUME_IGNITION).
    """
    is_call = str(direction).upper() in ("CALL", "BULLISH", "LONG")
    band = float(bb_upper_1d or 0.0) if is_call else float(bb_lower_1d or 0.0)
    threshold = get_options_runway_threshold(ticker)

    if open_price is None or open_price <= 0 or band <= 0:
        return {
            "approved": True, "mode": "NO_DATA", "base_runway_pct": None,
            "projected_runway_pct": None, "delta_rvol_pp": 0.0, "threshold_pct": threshold,
            "reason": "Sin datos de Open o banda 1D para evaluar Runway (no se bloquea)."
        }

    base = ((band - open_price) / open_price * 100.0) if is_call else ((open_price - band) / open_price * 100.0)
    band_name = "BB_UPPER_1D" if is_call else "BB_LOWER_1D"
    dir_name = "CALL" if is_call else "PUT"

    out = {
        "approved": False, "mode": "BLOCKED", "base_runway_pct": round(base, 2),
        "projected_runway_pct": round(base, 2), "delta_rvol_pp": 0.0,
        "threshold_pct": threshold, "reason": ""
    }

    if base >= threshold:
        out.update({
            "approved": True, "mode": "BASE",
            "reason": f"Runway 1D {dir_name} aprobado: +{base:.1f}% a {band_name} (${band:.2f}) >= {threshold:.1f}%."
        })
        return out

    pressure_word = "compradora" if is_call else "vendedora"
    if rvol < OPT_RUNWAY_MASSIVE_RVOL or not pressure_ok:
        out["reason"] = (
            f"{dir_name} EXCLUIDO por Runway 1D: espacio base +{base:.1f}% a {band_name} (${band:.2f}) "
            f"< {threshold:.1f}% y sin ignición de volumen (RVOL {rvol:.1f}x, requiere >= "
            f"{OPT_RUNWAY_MASSIVE_RVOL:.1f}x con presión {pressure_word})."
        )
        return out

    delta_pp = min(OPT_RUNWAY_MAX_DELTA_PP, OPT_RUNWAY_DELTA_PP_PER_RVOL * (rvol - 1.0))
    projected = base + delta_pp
    out["delta_rvol_pp"] = round(delta_pp, 2)
    out["projected_runway_pct"] = round(projected, 2)

    if projected >= threshold:
        out.update({
            "approved": True, "mode": "VOLUME_IGNITION",
            "reason": (
                f"Excepción por volumen: base +{base:.1f}% + Delta RVOL {rvol:.1f}x (+{delta_pp:.1f} pp) = "
                f"+{projected:.1f}% proyectado >= {threshold:.1f}%."
            )
        })
    else:
        out["reason"] = (
            f"{dir_name} EXCLUIDO por Runway 1D: aun con RVOL {rvol:.1f}x el espacio proyectado "
            f"+{projected:.1f}% (base +{base:.1f}% + {delta_pp:.1f} pp) < {threshold:.1f}%."
        )
    return out


def evaluate_options_rsi_exhaustion(
    direction: str,
    rsi_5m: Optional[float] = None,
    rsi_15m: Optional[float] = None,
    rsi_1h: Optional[float] = None,
) -> Dict[str, Any]:
    """CALLs: RSI no puede superar el techo. PUTs: RSI no puede estar bajo el piso. None = sin dato (omitido)."""
    is_call = str(direction).upper() in ("CALL", "BULLISH", "LONG")
    limits = OPT_RSI_LIMITS["CALL" if is_call else "PUT"]
    for label, key, val in (("5m", "5m", rsi_5m), ("15m", "15m", rsi_15m), ("1H", "1h", rsi_1h)):
        if val is None:
            continue
        lim = limits[key]
        if is_call and val > lim:
            return {"approved": False, "reason": f"CALL bloqueado por agotamiento: RSI {label} ({val:.1f}) > {lim:.0f}."}
        if (not is_call) and val < lim:
            return {"approved": False, "reason": f"PUT bloqueado por agotamiento vendedor: RSI {label} ({val:.1f}) < {lim:.0f}."}
    return {"approved": True, "reason": "RSI sin agotamiento."}


def evaluate_options_1h_trend(direction: str, ema3: float, ema9: float, ema3_prev: float) -> Dict[str, Any]:
    """
    Alineación tendencial estricta en 1H, sin bypass de apertura.
    CALL: EMA3 > EMA9 con EMA3 ascendente. PUT: EMA3 < EMA9 con EMA3 descendente.
    """
    is_call = str(direction).upper() in ("CALL", "BULLISH", "LONG")
    if is_call:
        if not ema3 > ema9:
            return {"approved": False, "reason": f"CALL bloqueado: EMA3 1H (${ema3:.2f}) <= EMA9 1H (${ema9:.2f})."}
        if not ema3 > ema3_prev:
            return {"approved": False, "reason": f"CALL bloqueado: pendiente EMA3 1H no ascendente (${ema3:.2f} <= ${ema3_prev:.2f})."}
    else:
        if not ema3 < ema9:
            return {"approved": False, "reason": f"PUT bloqueado: EMA3 1H (${ema3:.2f}) >= EMA9 1H (${ema9:.2f})."}
        if not ema3 < ema3_prev:
            return {"approved": False, "reason": f"PUT bloqueado: pendiente EMA3 1H no descendente (${ema3:.2f} >= ${ema3_prev:.2f})."}
    return {"approved": True, "reason": "Tendencia 1H alineada."}


def _compute_day_open_and_rvol(df_5m: Optional[pd.DataFrame]) -> Tuple[float, float]:
    """Open de la sesión actual (primera vela del último día) y RVOL 5m (última vela vs. media de hasta 20 previas)."""
    if df_5m is None or df_5m.empty:
        return 0.0, 1.0
    df_day = df_5m
    try:
        if isinstance(df_5m.index, pd.DatetimeIndex):
            last_date = df_5m.index[-1].date()
            df_day = df_5m[df_5m.index.date == last_date]
    except Exception:
        df_day = df_5m
    o = _safe_col(df_day, "open")
    day_open = float(o.iloc[0]) if len(o) > 0 else 0.0
    v = _safe_col(df_day, "volume")
    rvol = 1.0
    if len(v) >= 2:
        prior_avg = float(v.iloc[:-1].tail(20).mean())
        if prior_avg > 0:
            rvol = float(v.iloc[-1]) / prior_avg
    return day_open, rvol


def _directional_pressure_ok(df_5m: Optional[pd.DataFrame], is_call: bool) -> bool:
    """CALL: última vela 5m verde y sin caída vs. cierre previo. PUT: espejo."""
    if df_5m is None or df_5m.empty:
        return False
    c = _safe_col(df_5m, "close")
    o = _safe_col(df_5m, "open")
    last_c, last_o = float(c.iloc[-1]), float(o.iloc[-1])
    prev_c = float(c.iloc[-2]) if len(c) >= 2 else last_o
    return (last_c >= last_o and last_c >= prev_c) if is_call else (last_c <= last_o and last_c <= prev_c)


def _get_daily_bb_bounds(ticker: str, price: float) -> Tuple[float, float]:
    """(BB_UPPER_1D, BB_LOWER_1D) reutilizando el cache diario del escáner Alpha Runner."""
    from app.stocks import alpha_runner_scanner as ars
    _, bb_upper, _ = ars.get_daily_bollinger_metrics(ticker, price)
    clean = ticker.replace("/", "").replace(".", "").upper().strip()
    cached = ars._DAILY_BB_CACHE.get(clean)
    bb_lower = float(cached[3]) if cached else price * 0.7
    return float(bb_upper), bb_lower


def evaluate_options_entry_gatekeeper(
    ticker: str,
    direction: str,
    df_5m: Optional[pd.DataFrame],
    df_15m: Optional[pd.DataFrame],
    df_1h: Optional[pd.DataFrame],
    bb_upper_1d: float,
    bb_lower_1d: float,
    rvol: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Gatekeeper ADUANA Opciones de última milla: Daily Runway -> RSI MTF -> tendencia 1H.
    Devuelve {'approved', 'stage', 'reason', 'runway'}.
    """
    is_call = str(direction).upper() in ("CALL", "BULLISH", "LONG")
    day_open, rvol_calc = _compute_day_open_and_rvol(df_5m)
    rvol_eff = float(rvol) if rvol is not None else rvol_calc

    runway = evaluate_options_daily_runway(
        ticker, direction, day_open, bb_upper_1d, bb_lower_1d,
        rvol=rvol_eff, pressure_ok=_directional_pressure_ok(df_5m, is_call)
    )
    if not runway["approved"]:
        return {"approved": False, "stage": "RUNWAY", "reason": runway["reason"], "runway": runway}

    rsi_5m = rsi_15m = rsi_1h = None
    if df_5m is not None and len(df_5m) >= 15:
        rsi_5m = float(compute_rsi(_safe_col(df_5m, "close"), 14).iloc[-1])
    if df_15m is not None and len(df_15m) >= 15:
        rsi_15m = float(compute_rsi(_safe_col(df_15m, "close"), 14).iloc[-1])
    if df_1h is not None and len(df_1h) >= 15:
        rsi_1h = float(compute_rsi(_safe_col(df_1h, "close"), 14).iloc[-1])
    rsi_res = evaluate_options_rsi_exhaustion(direction, rsi_5m, rsi_15m, rsi_1h)
    if not rsi_res["approved"]:
        return {"approved": False, "stage": "RSI", "reason": rsi_res["reason"], "runway": runway}

    if df_1h is not None and len(df_1h) >= 10:
        c1h = _safe_col(df_1h, "close")
        ema3_s = c1h.ewm(span=3, adjust=False).mean()
        ema9_s = c1h.ewm(span=9, adjust=False).mean()
        trend = evaluate_options_1h_trend(direction, float(ema3_s.iloc[-1]), float(ema9_s.iloc[-1]), float(ema3_s.iloc[-2]))
        if not trend["approved"]:
            return {"approved": False, "stage": "TREND_1H", "reason": trend["reason"], "runway": runway}

    return {"approved": True, "stage": "OK", "reason": "ADUANA Opciones: Runway, RSI y tendencia 1H aprobados.", "runway": runway}


def fetch_and_evaluate_options_gatekeeper(ticker: str, direction: str, price: float) -> Dict[str, Any]:
    """Descarga datos (yfinance) y ejecuta el gatekeeper. Usado por el dispatcher autónomo."""
    import yfinance as yf
    clean = ticker.replace("/", "").replace(".", "").upper().strip()
    t = yf.Ticker(clean)
    df_5m = t.history(period="5d", interval="5m")
    df_1h = t.history(period="1mo", interval="1h")
    df_15m = None
    if df_5m is not None and not df_5m.empty:
        df_15m = df_5m.resample("15min").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        ).dropna()
    bb_upper, bb_lower = _get_daily_bb_bounds(clean, price)
    return evaluate_options_entry_gatekeeper(clean, direction, df_5m, df_15m, df_1h, bb_upper, bb_lower)


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
    direction: str = "CALL",
    df_market_ref: Optional[pd.DataFrame] = None,
    market_ref_symbol: str = "SPY"
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
        # ── PILAR 1 ADUANA OPCIONES: Daily Runway 1D (exclusión preventiva + excepción por volumen) ──
        try:
            bb_up_1d, bb_lo_1d = _get_daily_bb_bounds(ticker, cur_p)
            day_open_v, rvol_v = _compute_day_open_and_rvol(df_5m)
            runway_res = evaluate_options_daily_runway(
                ticker, direction, day_open_v, bb_up_1d, bb_lo_1d,
                rvol=rvol_v, pressure_ok=_directional_pressure_ok(df_5m, is_call)
            )
            res["runway"] = runway_res
            if not runway_res["approved"]:
                res["reason"] = runway_res["reason"]
                return res
        except Exception as e_runway_opt:
            log_warning(MODULE, f"Aviso evaluando Daily Runway de opciones para {ticker}: {e_runway_opt}")

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

        # ── PILAR 2 ADUANA OPCIONES: Anti-agotamiento RSI multi-timeframe (5m / 15m / 1H) ──
        rsi_5m_opt = None
        if df_5m is not None and len(df_5m) >= 15:
            rsi_5m_opt = float(compute_rsi(_safe_col(df_5m, "close"), period=14).iloc[-1])
        rsi_15m_opt = None
        if df_15m is not None and len(df_15m) >= 15:
            rsi_15m_opt = float(compute_rsi(_safe_col(df_15m, "close"), period=14).iloc[-1])
        rsi_gate = evaluate_options_rsi_exhaustion(direction, rsi_5m_opt, rsi_15m_opt, cur_rsi_1h)
        if not rsi_gate["approved"]:
            res["reason"] = rsi_gate["reason"]
            return res

        delta_bb = 0.10 * (bb_upper_1h - bb_basis_1h)

        # Reglas 1H para CALL
        if is_call:
            if cur_open_1h >= (bb_upper_1h - delta_bb):
                res["reason"] = f"CALL bloqueado: Open 1H (${cur_open_1h:.2f}) sin espacio ante Banda Superior (${bb_upper_1h:.2f})"
                return res
            if cur_rsi_1h >= 80.0:
                res["reason"] = f"CALL bloqueado: RSI 1H ({cur_rsi_1h:.1f}) >= 80 (posible agotamiento inicial)"
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

        # Candado estricto 1H sin bypass por Open vs EMA9:
        # CALL exige EMA3 > EMA9 con EMA3 ascendente; PUT exige EMA3 < EMA9 con EMA3 descendente.
        trend_gate = evaluate_options_1h_trend(direction, cur_ema3, cur_ema9, prev_ema3)
        if not trend_gate["approved"]:
            res["reason"] = trend_gate["reason"]
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
            if sipv_signal and str(sipv_signal).upper() not in ("BUY", "STRONG_BUY", "ALCISTA"):
                res["reason"] = f"CALL bloqueado: SIPV indica '{sipv_signal}' en vez de BUY"
                return res

            if len(df_5m) == 2:
                # Ruta A: Apertura directa
                if c1 <= o1:
                    res["reason"] = f"CALL bloqueado: Vela 1 de 5m fue roja (Close ${c1:.2f} <= Open ${o1:.2f})"
                    return res
                if o2 < (c1 * 0.998):
                    res["reason"] = f"CALL bloqueado: Vela 2 de 5m abrió por debajo del cierre previo (Open ${o2:.2f} < Close ${c1:.2f})"
                    return res

                initial_sl = round(min(l1, o1 * 0.995), 2)
                rule_code = "OPT_GAP_TRANCHE_1_CALL"
                reason_msg = f"CALL Tranche 1 aprobado: Vela 1 verde (+${c1-o1:.2f}), Vela 2 continuación micro-gap (Open ${o2:.2f}), Macro 1H con espacio."
            else:
                # len(df_5m) >= 3: Verificar si hubo sacudida previa (velas rojas)
                had_red = bool(np.any(c5m.iloc[:-2].to_numpy() <= o5m.iloc[:-2].to_numpy()))
                if had_red:
                    # Ruta B: Dip & Rip / Gap Fill & Rip
                    is_turn_green_1 = c1 > o1
                    is_turn_green_2 = (c2 >= o2) and (c2 >= c1)

                    if is_turn_green_1 and is_turn_green_2:
                        low_dip = float(min(float(np.min(l5m.iloc[:-2].to_numpy())), l1))
                        open_day = float(o5m.iloc[0])
                        est_prev_close = open_day / (1.0 + (gap_pct / 100.0)) if gap_pct > 0 else open_day * 0.95

                        # Candado anti-desplome con tolerancia de mecha del 3% bajo el cierre previo
                        is_gap_fill_sweep = (low_dip <= est_prev_close * 1.01) and (low_dip >= est_prev_close * 0.97)

                        if low_dip < (est_prev_close * 0.97):
                            res["reason"] = f"CALL Dip & Rip bloqueado: sacudida perforó cierre previo (${est_prev_close:.2f}) por más del 3%"
                            return res

                        if low_dip < est_prev_close and cur_p < est_prev_close:
                            res["reason"] = f"CALL Gap Fill en curso: esperando que recupere cierre previo (${est_prev_close:.2f}, actual ${cur_p:.2f})"
                            return res

                        if not is_gap_fill_sweep:
                            initial_gap_pts = open_day - est_prev_close
                            if initial_gap_pts > 0:
                                max_drop = open_day - (0.80 * initial_gap_pts)
                                if low_dip < max_drop:
                                    res["reason"] = f"CALL Dip & Rip bloqueado: retroceso borró más del 80% del Gap inicial (Low ${low_dip:.2f} < ${max_drop:.2f})"
                                    return res

                        delta = max(0.01 * cur_p, 0.15 * float(h1 - l1))
                        initial_sl = round(low_dip - delta, 2)
                        if initial_sl <= 0 or initial_sl >= cur_p:
                            initial_sl = round(low_dip * 0.99, 2)

                        rule_code = "OPT_GAP_DIP_AND_RIP_CALL"
                        fill_tag = " (Gap Fill)" if is_gap_fill_sweep else ""
                        reason_msg = f"Dip & Rip Tranche 1 aprobado{fill_tag}: Sacudida inicial absorbida (Low ${low_dip:.2f}), confirmación 2 velas verdes (${c1:.2f}->${c2:.2f}), Macro 1H con espacio."
                        res.update({
                            "should_enter": True,
                            "tranche_step": 1,
                            "tranche_contracts_ratio": 0.3333,
                            "rule_code": rule_code,
                            "initial_sl_underlying": initial_sl,
                            "reason": reason_msg
                        })
                        return res

                # ESTRATEGIA 2: ORB 15m Breakout (CALLs)
                if len(df_5m) >= 4:
                    h15_range = float(np.max(h5m.iloc[:3].to_numpy()))
                    l15_range = float(np.min(l5m.iloc[:3].to_numpy()))
                    if cur_p > h15_range and c2 > o2:
                        initial_sl = round(min(l15_range, cur_p * 0.97), 2)
                        res.update({
                            "should_enter": True,
                            "tranche_step": 1,
                            "tranche_contracts_ratio": 0.3333,
                            "rule_code": "OPT_GAP_ORB_CALL",
                            "initial_sl_underlying": initial_sl,
                            "reason": f"CALL ORB 15m Breakout aprobado: Superó techo de apertura (${h15_range:.2f}), SL=${initial_sl:.2f}."
                        })
                        return res

                # ESTRATEGIA 3: VWAP Reload (CALLs)
                if len(df_5m) >= 6:
                    vwap_series = compute_vwap(df_5m)
                    cur_vwap = float(vwap_series.iloc[-1]) if len(vwap_series) > 0 else 0.0
                    if cur_vwap > 0 and cur_p >= cur_vwap:
                        recent_lows = l5m.iloc[-3:].to_numpy()
                        if np.any((recent_lows <= cur_vwap * 1.004) & (recent_lows >= cur_vwap * 0.990)) and c2 > o2:
                            test_low = float(np.min(recent_lows))
                            initial_sl = round(test_low * 0.995, 2)
                            res.update({
                                "should_enter": True,
                                "tranche_step": 1,
                                "tranche_contracts_ratio": 0.3333,
                                "rule_code": "OPT_GAP_VWAP_CALL",
                                "initial_sl_underlying": initial_sl,
                                "reason": f"CALL VWAP Reload aprobado: Rebote en VWAP (${cur_vwap:.2f}) con vela verde, SL=${initial_sl:.2f}."
                            })
                            return res

                if not had_red:
                    # No hubo rojas: Continuación directa
                    if c1 <= o1:
                        res["reason"] = f"CALL bloqueado: Vela anterior de 5m fue roja (Close ${c1:.2f} <= Open ${o1:.2f})"
                        return res
                    if o2 < (c1 * 0.998):
                        res["reason"] = f"CALL bloqueado: Vela actual de 5m abrió por debajo del cierre previo (Open ${o2:.2f} < Close ${c1:.2f})"
                        return res

                    initial_sl = round(min(l1, o1 * 0.995), 2)
                    rule_code = "OPT_GAP_TRANCHE_1_CALL"
                    reason_msg = f"CALL Tranche 1 aprobado: Vela previa verde (+${c1-o1:.2f}), Vela actual micro-gap (Open ${o2:.2f}), Macro 1H con espacio."
                    res.update({
                        "should_enter": True,
                        "tranche_step": 1,
                        "tranche_contracts_ratio": 0.3333,
                        "rule_code": rule_code,
                        "initial_sl_underlying": initial_sl,
                        "reason": reason_msg
                    })
                    return res

                if had_red:
                    if not is_turn_green_1:
                        res["reason"] = f"CALL bloqueado: vela previa de 5m sigue roja (Close ${c1:.2f} <= Open ${o1:.2f})"
                    elif not is_turn_green_2:
                        res["reason"] = f"CALL bloqueado: vela 2 de confirmación no superó la anterior (Close ${c2:.2f} vs Prev ${c1:.2f})"
                    return res

        else:
            if sipv_signal and str(sipv_signal).upper() not in ("SELL", "STRONG_SELL", "BAJISTA"):
                res["reason"] = f"PUT bloqueado: SIPV indica '{sipv_signal}' en vez de SELL"
                return res

            # MEJORA 1: MARKET DIRECTIONAL GATE (SPY / QQQ)
            if df_market_ref is not None and len(df_market_ref) >= 2:
                market_vwap_series = compute_vwap(df_market_ref)
                if len(market_vwap_series) > 0:
                    cur_m_vwap = float(market_vwap_series.iloc[-1])
                    cur_m_p = float(_safe_col(df_market_ref, "close").iloc[-1])
                    if cur_m_p > (cur_m_vwap * 1.0005):
                        res["reason"] = (
                            f"PUT bloqueado por Market Gate: Mercado rector ({market_ref_symbol} ${cur_m_p:.2f}) "
                            f"cotiza sobre su VWAP (${cur_m_vwap:.2f}) en tendencia alcista. Riesgo extremo de squeeze."
                        )
                        return res

            if len(df_5m) == 2:
                # Ruta A: Apertura directa bajista
                if c1 >= o1:
                    res["reason"] = f"PUT bloqueado: Vela 1 de 5m fue verde (Close ${c1:.2f} >= Open ${o1:.2f})"
                    return res
                if o2 > (c1 * 1.002):
                    res["reason"] = f"PUT bloqueado: Vela 2 de 5m abrió por encima del cierre previo (Open ${o2:.2f} > Close ${c1:.2f})"
                    return res
                if c2 >= l1:
                    res["reason"] = f"PUT bloqueado en apertura: Vela 2 (${c2:.2f}) no perforó el mínimo de Vela 1 (${l1:.2f}). Sin expansión bajista."
                    return res

                # MEJORA 2: FILTRO DE VWAP INTRADÍA DEL SUBYACENTE PARA PUTS
                und_vwap_s = compute_vwap(df_5m)
                if len(und_vwap_s) > 0:
                    cur_und_vwap = float(und_vwap_s.iloc[-1])
                    if cur_p > (cur_und_vwap * 1.001):
                        res["reason"] = (
                            f"PUT bloqueado: Subyacente (${cur_p:.2f}) cotiza sobre su VWAP (${cur_und_vwap:.2f}). "
                            f"Absorción compradora activa, prohibido comprar PUTs."
                        )
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
            else:
                # MEJORA 2: FILTRO DE VWAP INTRADÍA DEL SUBYACENTE PARA PUTS (>= 3 velas)
                und_vwap_s = compute_vwap(df_5m)
                if len(und_vwap_s) > 0:
                    cur_und_vwap = float(und_vwap_s.iloc[-1])
                    if cur_p > (cur_und_vwap * 1.001):
                        res["reason"] = (
                            f"PUT bloqueado: Subyacente (${cur_p:.2f}) cotiza sobre su VWAP (${cur_und_vwap:.2f}). "
                            f"Absorción compradora activa, prohibido comprar PUTs."
                        )
                        return res

                # len(df_5m) >= 3: Verificar si hubo rebote matutino (velas verdes)
                had_green = bool(np.any(c5m.iloc[:-2].to_numpy() >= o5m.iloc[:-2].to_numpy()))
                if had_green:
                    # Ruta B: Pop & Drop / Gap Fill & Drop
                    is_turn_red_1 = c1 < o1
                    is_turn_red_2 = (c2 <= o2) and (c2 <= c1)

                    if is_turn_red_1 and is_turn_red_2:
                        high_pop = float(max(float(np.max(h5m.iloc[:-2].to_numpy())), h1))
                        open_day = float(o5m.iloc[0])
                        est_prev_close = open_day / (1.0 + (gap_pct / 100.0)) if gap_pct < 0 else open_day * 1.05

                        # Candado anti-reversión con tolerancia de mecha del 3% sobre el cierre previo
                        is_gap_fill_sweep = (high_pop >= est_prev_close * 0.99) and (high_pop <= est_prev_close * 1.03)

                        if high_pop > (est_prev_close * 1.03):
                            res["reason"] = f"PUT Pop & Drop bloqueado: rebote perforó cierre previo (${est_prev_close:.2f}) por más del 3%"
                            return res

                        if high_pop > est_prev_close and cur_p > est_prev_close:
                            res["reason"] = f"PUT Gap Fill en curso: esperando que caiga bajo el cierre previo (${est_prev_close:.2f}, actual ${cur_p:.2f})"
                            return res

                        if not is_gap_fill_sweep:
                            initial_gap_pts = est_prev_close - open_day
                            if initial_gap_pts > 0:
                                max_bounce = open_day + (0.80 * initial_gap_pts)
                                if high_pop > max_bounce:
                                    res["reason"] = f"PUT Pop & Drop bloqueado: rebote borró más del 80% del Gap inicial bajista (High ${high_pop:.2f} > ${max_bounce:.2f})"
                                    return res

                        # MEJORA 3: FILTRO ANTI-DOBLE SUELO EN POP & DROP
                        min_day_low = float(np.min(l5m.iloc[:-1].to_numpy()))
                        if cur_p > (min_day_low * 1.008):
                            res["reason"] = (
                                f"PUT Pop & Drop bloqueado: Precio (${cur_p:.2f}) flota sobre mínimo previo (${min_day_low:.2f}) "
                                f"sin quiebre bajista (Riesgo de Doble Suelo)."
                            )
                            return res

                        if not is_gap_fill_sweep:
                            initial_gap_pts = est_prev_close - open_day
                            if initial_gap_pts > 0:
                                max_bounce = open_day + (0.80 * initial_gap_pts)
                                if high_pop > max_bounce:
                                    res["reason"] = f"PUT Pop & Drop bloqueado: rebote borró más del 80% del Gap inicial bajista (High ${high_pop:.2f} > ${max_bounce:.2f})"
                                    return res

                        delta = max(0.01 * cur_p, 0.15 * float(h1 - l1))
                        initial_sl = round(high_pop + delta, 2)
                        if initial_sl <= cur_p:
                            initial_sl = round(high_pop * 1.01, 2)

                        rule_code = "OPT_GAP_POP_AND_DROP_PUT"
                        fill_tag = " (Gap Fill)" if is_gap_fill_sweep else ""
                        reason_msg = f"Pop & Drop Tranche 1 aprobado{fill_tag}: Rebote inicial rechazado (High ${high_pop:.2f}), confirmación 2 velas rojas (${c1:.2f}->${c2:.2f}), Macro 1H con espacio."
                        res.update({
                            "should_enter": True,
                            "tranche_step": 1,
                            "tranche_contracts_ratio": 0.3333,
                            "rule_code": rule_code,
                            "initial_sl_underlying": initial_sl,
                            "reason": reason_msg
                        })
                        return res

                # ESTRATEGIA 2: ORB 15m Breakdown (PUTs)
                if len(df_5m) >= 4:
                    l15_range = float(np.min(l5m.iloc[:3].to_numpy()))
                    h15_range = float(np.max(h5m.iloc[:3].to_numpy()))
                    if cur_p < l15_range and c2 < o2:
                        initial_sl = round(max(h15_range, cur_p * 1.03), 2)
                        res.update({
                            "should_enter": True,
                            "tranche_step": 1,
                            "tranche_contracts_ratio": 0.3333,
                            "rule_code": "OPT_GAP_ORB_PUT",
                            "initial_sl_underlying": initial_sl,
                            "reason": f"PUT ORB 15m Breakdown aprobado: Perforó piso de apertura (${l15_range:.2f}), SL=${initial_sl:.2f}."
                        })
                        return res

                # ESTRATEGIA 3: VWAP Rejection (PUTs)
                if len(df_5m) >= 6:
                    vwap_series = compute_vwap(df_5m)
                    cur_vwap = float(vwap_series.iloc[-1]) if len(vwap_series) > 0 else 0.0
                    if cur_vwap > 0 and cur_p <= cur_vwap:
                        recent_highs = h5m.iloc[-3:].to_numpy()
                        if np.any((recent_highs >= cur_vwap * 0.996) & (recent_highs <= cur_vwap * 1.010)) and c2 < o2:
                            test_high = float(np.max(recent_highs))
                            initial_sl = round(test_high * 1.005, 2)
                            res.update({
                                "should_enter": True,
                                "tranche_step": 1,
                                "tranche_contracts_ratio": 0.3333,
                                "rule_code": "OPT_GAP_VWAP_PUT",
                                "initial_sl_underlying": initial_sl,
                                "reason": f"PUT VWAP Rejection aprobado: Rechazo en VWAP (${cur_vwap:.2f}) con vela roja, SL=${initial_sl:.2f}."
                            })
                            return res

                if not had_green:
                    # No hubo verdes: Continuación directa bajista
                    if c1 >= o1:
                        res["reason"] = f"PUT bloqueado: Vela anterior de 5m fue verde (Close ${c1:.2f} >= Open ${o1:.2f})"
                        return res
                    if o2 > (c1 * 1.002):
                        res["reason"] = f"PUT bloqueado: Vela actual de 5m abrió por encima del cierre previo (Open ${o2:.2f} > Close ${c1:.2f})"
                        return res

                    initial_sl = round(max(h1, o1 * 1.005), 2)
                    rule_code = "OPT_GAP_TRANCHE_1_PUT"
                    reason_msg = f"PUT Tranche 1 aprobado: Vela previa roja (-${o1-c1:.2f}), Vela actual bajista (Open ${o2:.2f}), Macro 1H con espacio."
                    res.update({
                        "should_enter": True,
                        "tranche_step": 1,
                        "tranche_contracts_ratio": 0.3333,
                        "rule_code": rule_code,
                        "initial_sl_underlying": initial_sl,
                        "reason": reason_msg
                    })
                    return res

                if had_green:
                    if not is_turn_red_1:
                        res["reason"] = f"PUT bloqueado: vela previa de 5m sigue verde (Close ${c1:.2f} >= Open ${o1:.2f})"
                    elif not is_turn_red_2:
                        res["reason"] = f"PUT bloqueado: vela 2 de confirmación no cayó bajo la anterior (Close ${c2:.2f} vs Prev ${c1:.2f})"
                    return res

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
            if is_call and cur_rsi_1h >= 80.0:
                res["reason"] = f"Tranche 3 CALL bloqueado: RSI 1H ({cur_rsi_1h:.1f}) >= 80"
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

    # 1. HARD STOP LOSS EN PRIMA (-35%) — Solo si tiene >= 5 min de maduración y cotización real
    has_live_quote = bool(position.get("has_live_opt_quote", True))
    if position_age_minutes >= 5.0 and has_live_quote and unrealized_pnl_pct <= -35.0:
        res.update({
            "should_exit": True,
            "exit_type": "hard_stop",
            "contracts_ratio_to_exit": 1.0,
            "rule_code": "OPT_GAP_HARD_SL_PREM",
            "reason": f"Hard SL activado: Prima cae {unrealized_pnl_pct:.1f}% <= -35.0% (${current_option_premium:.2f} vs compra ${entry_premium:.2f})"
        })
        return res

    # 2. STALL GUARD POR THETA DECAY (20 min estancado)
    # Solo aplica para contratos intradía 0-3 DTE. Prohibido para multi-semana swing (DTE >= 4)
    exp_str_sg = str(position.get("expiry") or "")
    dte_val_sg = 0
    if len(exp_str_sg) >= 10:
        try:
            from datetime import date
            dte_val_sg = (date.fromisoformat(exp_str_sg[:10]) - datetime.now(timezone.utc).date()).days
        except Exception:
            pass

    reentry_count = int(position.get("reentry_count") or 0)
    if dte_val_sg < 4 and position_age_minutes >= 20.0 and reentry_count == 0 and unrealized_pnl_pct <= -15.0:
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

    # PILAR 3 (OPCIONES): BLINDAJE RÁPIDO BREAKEVEN PARA CALLs Y PUTs (+5.0% subyacente o prima -> BE + 1% Lock)
    und_entry_p = float(position.get("entry_underlying_price") or position.get("entry_price") or 0.0)
    und_pnl_pct = 0.0
    if und_entry_p > 0:
        und_pnl_pct = ((current_underlying_price - und_entry_p) / und_entry_p * 100.0) if is_call else ((und_entry_p - current_underlying_price) / und_entry_p * 100.0)

    # Regla Institucional: Al avanzar +5% en subyacente o prima, blindar en (precio compra + 1%)
    if (peak_pnl_pct >= 5.0 or und_pnl_pct >= 5.0) and peak_pnl_pct < 25.0:
        if current_option_premium <= entry_premium * 1.01:
            res.update({
                "should_exit": True,
                "exit_type": "trailing_stop",
                "contracts_ratio_to_exit": 1.0,
                "rule_code": "OPT_GAP_BE_LOCK_PLUS_1PCT",
                "reason": f"Breakeven Lock (+1% Protegido) {'CALL' if is_call else 'PUT'}: Ganancia previa superó +5% (prima +{peak_pnl_pct:.1f}%, subyacente +{und_pnl_pct:.2f}%). Prima protege compra + 1% (${entry_premium*1.01:.2f})"
            })
            return res

    # SALIDAS DEFENSIVAS ANTE ROTURA DE VWAP EN SUBYACENTE (CALLs y PUTs)
    if df_5m is not None and len(df_5m) >= 3:
        vwap_s = compute_vwap(df_5m)
        if len(vwap_s) > 0:
            cur_vwap = float(vwap_s.iloc[-1])
            cur_stock_p = float(_safe_col(df_5m, "close").iloc[-1])
            if not is_call and cur_stock_p > (cur_vwap * 1.003) and unrealized_pnl_pct <= -5.0:
                res.update({
                    "should_exit": True,
                    "exit_type": "vwap_breached",
                    "contracts_ratio_to_exit": 1.0,
                    "rule_code": "OPT_GAP_PUT_EXIT_VWAP",
                    "reason": f"Salida Defensiva PUT: Subyacente (${cur_stock_p:.2f}) recuperó su VWAP (${cur_vwap:.2f}) al alza. Riesgo de squeeze cortado anticipadamente."
                })
                return res
            elif is_call and cur_stock_p < (cur_vwap * 0.996) and unrealized_pnl_pct <= -5.0:
                res.update({
                    "should_exit": True,
                    "exit_type": "vwap_breached",
                    "contracts_ratio_to_exit": 1.0,
                    "rule_code": "OPT_GAP_CALL_EXIT_VWAP",
                    "reason": f"Salida Defensiva CALL: Subyacente (${cur_stock_p:.2f}) perforó su VWAP (${cur_vwap:.2f}) a la baja (-0.4%). Riesgo cortado anticipadamente."
                })
                return res

    # 3.B. TAKE PROFIT ESTRUCTURAL POR PROXIMIDAD A MURO (<= 0.8% - SALIDA MARKET INMEDIATA)
    sym_opt = str(position.get("symbol") or "").upper().strip()
    p_opt_eval = current_underlying_price
    if sym_opt and p_opt_eval > 0 and unrealized_pnl_pct >= 8.0:
        try:
            from app.core.structural_regime_engine import evaluate_structural_regime
            st_reg_opt = evaluate_structural_regime(sym_opt, p_opt_eval)
            target_wall = float(st_reg_opt.get("target_resistance_wall") or 0.0)
            target_ceiling = float(st_reg_opt.get("target_ceiling") or 0.0)
            target_floor = float(st_reg_opt.get("key_levels_1d", {}).get("bb_lower") or 0.0)

            if is_call:
                rel_target = target_wall if (target_wall > p_opt_eval and target_wall < target_ceiling) else target_ceiling
                if rel_target > 0:
                    dist_to_wall = ((rel_target - p_opt_eval) / p_opt_eval) * 100.0
                    if dist_to_wall <= 0.80:
                        res.update({
                            "should_exit": True,
                            "exit_type": "take_profit_structural_proximity",
                            "contracts_ratio_to_exit": 1.0,
                            "rule_code": "OPT_STRUCTURAL_TARGET_NEAR_TP",
                            "reason": f"Take Profit Estructural CALL (Proximidad {dist_to_wall:.2f}% <= 0.8%): Subyacente ${p_opt_eval:.2f} a las puertas de muro institucional ${rel_target:.2f}. Salida MARKET inmediata para evitar front-running."
                        })
                        return res
            else:
                if target_floor > 0:
                    dist_to_floor = ((p_opt_eval - target_floor) / p_opt_eval) * 100.0
                    if dist_to_floor <= 0.80:
                        res.update({
                            "should_exit": True,
                            "exit_type": "take_profit_structural_proximity",
                            "contracts_ratio_to_exit": 1.0,
                            "rule_code": "OPT_STRUCTURAL_TARGET_NEAR_TP",
                            "reason": f"Take Profit Estructural PUT (Proximidad {dist_to_floor:.2f}% <= 0.8%): Subyacente ${p_opt_eval:.2f} rozando soporte institucional ${target_floor:.2f}. Salida MARKET inmediata para asegurar pico."
                        })
                        return res
        except Exception:
            pass

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

            # Breakeven Lock + 1% para CALLs (+5% subyacente -> SL al precio de compra + 1%)
            if und_entry_p > 0 and current_underlying_price >= round(und_entry_p * 1.05, 2):
                sl_be_plus_1 = round(und_entry_p * 1.01, 2)
                if sl_be_plus_1 > (res["new_stop_loss_underlying"] or current_sl):
                    res["new_stop_loss_underlying"] = sl_be_plus_1
                    res["rule_code"] = "BE_LOCK_PLUS_1PCT"

            # Si el precio perfora el SL actual (con ventana mínima de 5 min tras la apertura)
            active_sl = res["new_stop_loss_underlying"] or current_sl
            if position_age_minutes >= 5.0 and active_sl > 0.0 and current_underlying_price <= active_sl:
                res.update({
                    "should_exit": True,
                    "exit_type": "stop_loss_underlying",
                    "contracts_ratio_to_exit": 1.0,
                    "rule_code": res.get("rule_code") or "OPT_GAP_SL_EMA9_15M",
                    "reason": f"SL Técnico perforado: Subyacente (${current_underlying_price:.2f}) <= SL (${active_sl:.2f})"
                })
                return res
        else:
            # En PUTs, el SL del subyacente es un techo. Si EMA9 baja, reducir techo
            if cur_ema9_15m < prev_ema9_15m:
                proposed_sl = round(cur_ema9_15m + delta_sl, 2)
                if current_sl == 0.0 or proposed_sl < current_sl:
                    res["new_stop_loss_underlying"] = proposed_sl
                    res["rule_code"] = "OPT_GAP_SL_EMA9_15M"

            # Breakeven Lock - 1% para PUTs a la inversa (-5% subyacente -> SL techo al precio de compra - 1%)
            if und_entry_p > 0 and current_underlying_price <= round(und_entry_p * 0.95, 2):
                sl_be_minus_1 = round(und_entry_p * 0.99, 2)
                curr_sl_target = res["new_stop_loss_underlying"] or current_sl
                if curr_sl_target == 0.0 or sl_be_minus_1 < curr_sl_target:
                    res["new_stop_loss_underlying"] = sl_be_minus_1
                    res["rule_code"] = "BE_LOCK_PLUS_1PCT"

            active_sl = res["new_stop_loss_underlying"] or current_sl
            if position_age_minutes >= 5.0 and active_sl > 0.0 and current_underlying_price >= active_sl:
                res.update({
                    "should_exit": True,
                    "exit_type": "stop_loss_underlying",
                    "contracts_ratio_to_exit": 1.0,
                    "rule_code": res.get("rule_code") or "OPT_GAP_SL_EMA9_15M",
                    "reason": f"SL Técnico perforado: Subyacente (${current_underlying_price:.2f}) >= SL (${active_sl:.2f})"
                })
                return res

    return res


# ══════════════════════════════════════════════════════════════════════════
# REGLA 4: VERIFICACIÓN DE OPCIONABILIDAD Y SIMBOLOS AUTORIZADOS
# ══════════════════════════════════════════════════════════════════════════

KNOWN_OPTIONABLE_SYMBOLS = {
    "SPY", "QQQ", "IWM", "DIA", "SMH", "XLE", "XLK", "XLF", "XLI", "XLV", "XLU",
    "NVDA", "AAPL", "MSFT", "TSLA", "AMD", "AMZN", "META", "GOOGL", "GOOG", "NFLX",
    "PLTR", "COIN", "AVGO", "INTC", "DIS", "BA", "BABA", "CRM", "UBER", "M", "AAL", "TLK"
}


def is_optionable(symbol: str, supabase: Any = None) -> bool:
    """
    Verifica si un ticker es apto para operar opciones en el sistema eTrade.
    Prioriza ETFs de alta liquidez y Mega-Caps, o consulta la tabla opt_underlyings.
    """
    sym = str(symbol or "").strip().upper()
    if sym in KNOWN_OPTIONABLE_SYMBOLS:
        return True
    if supabase is not None:
        try:
            r = supabase.table("opt_underlyings").select("optionable").eq("symbol", sym).limit(1).execute()
            if r.data:
                return bool(r.data[0].get("optionable", False))
        except Exception:
            pass
    return False

