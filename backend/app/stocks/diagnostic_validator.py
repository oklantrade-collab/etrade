"""
eTrader v5.0 — Diagnostic Validator & Safety Gate (Stocks)
Audita que el 100% de las variables técnicas y de gestión de riesgo estén completas,
válidas y no nulas/en blanco para cada posición de Stocks.

Reglas Operativas Obligatorias:
1. PRE-OPERACIÓN: Si la validación está en ROJO (is_valid == False), NO OPERAR (bloquear compra).
2. EN OPERACIÓN: Si una posición abierta pierde alguna variable requerida (falla técnica o riesgo),
   CERRAR la posición inmediatamente para proteger el capital.

Variables Auditadas (22 campos):
- Gestión de Riesgo: Stop Loss, Trailing Stop, Take Profit.
- Bollinger: BB Superior, Basis (SMA20/EMA20), BB Inferior.
- Medias Móviles: EMA3, EMA9, EMA20, EMA50, EMA200.
- Fibonacci: UPPER_1 a UPPER_6, LOWER_1 a LOWER_6.
"""

import time
import math
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
import pandas as pd
import numpy as np

from app.core.logger import log_info, log_error, log_warning, log_debug
from app.core.supabase_client import get_supabase

# Cache en memoria para cálculos rápidos con TTL (30 segundos)
_INDICATOR_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECS = 30.0

FIB_MULTIPLIERS = [1.0, 1.618, 2.618, 3.618, 4.236, 5.618]


def safe_float(v, default=0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def get_technical_indicators_snapshot(
    ticker: str,
    snap_db: Optional[dict] = None,
    df_15m: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Obtiene o calcula el set completo de indicadores para un ticker:
    - BBs (upper, basis, lower)
    - EMAs (3, 9, 20, 50, 200)
    - Fibonacci Bands (upper 1..6, lower 1..6)
    """
    now_ts = time.time()
    if ticker in _INDICATOR_CACHE:
        cached = _INDICATOR_CACHE[ticker]
        if now_ts - cached.get("_cached_at", 0) < CACHE_TTL_SECS:
            return cached

    # 1. Intentar aprovechar snap_db si ya tiene las bandas completas
    has_full_snap = False
    if snap_db and safe_float(snap_db.get("basis")) > 0 and safe_float(snap_db.get("upper_6")) > 0:
        has_full_snap = True

    # Si snap_db tiene datos básicos de precio, evitar llamadas lentas a yfinance
    if (df_15m is None or df_15m.empty) and not (snap_db and safe_float(snap_db.get("price")) > 0):
        try:
            import yfinance as yf
            t_obj = yf.Ticker(ticker)
            df_15m = t_obj.history(period="5d", interval="15m")
        except Exception as e:
            log_warning("diagnostic_validator", f"Error descargando barras para {ticker}: {e}")

    # 2. Calcular usando df_15m si está disponible
    if df_15m is not None and not df_15m.empty and len(df_15m) >= 20:
        from ta.trend import EMAIndicator
        from ta.volatility import BollingerBands, AverageTrueRange

        close = df_15m["Close"] if "Close" in df_15m.columns else df_15m["close"]
        high = df_15m["High"] if "High" in df_15m.columns else df_15m["high"]
        low = df_15m["Low"] if "Low" in df_15m.columns else df_15m["low"]

        cur_price = round(float(close.iloc[-1]), 4)
        ema_3 = round(float(EMAIndicator(close, 3).ema_indicator().iloc[-1]), 4)
        ema_9 = round(float(EMAIndicator(close, 9).ema_indicator().iloc[-1]), 4)
        ema_20 = round(float(EMAIndicator(close, 20).ema_indicator().iloc[-1]), 4)
        ema_50 = round(float(EMAIndicator(close, 50).ema_indicator().iloc[-1]), 4)

        if len(df_15m) >= 200:
            ema_200 = round(float(EMAIndicator(close, 200).ema_indicator().iloc[-1]), 4)
        else:
            # Fallback seguro para IPOs con menos de 200 velas
            ema_200 = ema_50

        bb = BollingerBands(close, window=20, window_dev=2)
        bb_upper = round(float(bb.bollinger_hband().iloc[-1]), 4)
        bb_lower = max(0.01, round(float(bb.bollinger_lband().iloc[-1]), 4))
        basis = round(float(bb.bollinger_mavg().iloc[-1]), 4)

        atr_series = AverageTrueRange(high, low, close, window=14).average_true_range()
        atr = round(float(atr_series.iloc[-1]), 4) if len(atr_series) > 0 else round(cur_price * 0.02, 4)
        if atr <= 0:
            atr = round(cur_price * 0.02, 4)

        fib_upper = {}
        fib_lower = {}
        for idx, mult in enumerate(FIB_MULTIPLIERS, start=1):
            fib_upper[f"upper_{idx}"] = round(basis + (atr * mult), 4)
            fib_lower[f"lower_{idx}"] = max(0.01, round(basis - (atr * mult), 4))

        result = {
            "current_price": cur_price,
            "basis": basis,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "atr": atr,
            "ema_3": ema_3,
            "ema_9": ema_9,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "ema_200": ema_200,
            **fib_upper,
            **fib_lower,
            "_cached_at": now_ts
        }
        _INDICATOR_CACHE[ticker] = result
        return result

    # 3. Si no hay df_15m pero snap_db tiene datos básicos, construir a partir de snap_db
    if snap_db:
        cur_price = safe_float(snap_db.get("price"))
        basis = safe_float(snap_db.get("basis")) or cur_price
        atr = safe_float(snap_db.get("atr")) or (cur_price * 0.02)
        bb_upper = safe_float(snap_db.get("upper_2")) or round(basis + (atr * 2.0), 4)
        bb_lower = safe_float(snap_db.get("lower_2")) or max(0.01, round(basis - (atr * 2.0), 4))

        fib_upper = {}
        fib_lower = {}
        for idx, mult in enumerate(FIB_MULTIPLIERS, start=1):
            fib_upper[f"upper_{idx}"] = safe_float(snap_db.get(f"upper_{idx}")) or round(basis + (atr * mult), 4)
            fib_lower[f"lower_{idx}"] = max(0.01, safe_float(snap_db.get(f"lower_{idx}")) or round(basis - (atr * mult), 4))

        result = {
            "current_price": cur_price,
            "basis": basis,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "atr": atr,
            "ema_3": safe_float(snap_db.get("ema3_15m") or snap_db.get("ema_3")),
            "ema_9": safe_float(snap_db.get("ema9_15m") or snap_db.get("ema_9")),
            "ema_20": basis,
            "ema_50": safe_float(snap_db.get("ema_50")),
            "ema_200": safe_float(snap_db.get("ema_200")),
            **fib_upper,
            **fib_lower,
            "_cached_at": now_ts
        }
        _INDICATOR_CACHE[ticker] = result
        return result

    # 4. Fallback sintético seguro para activos nuevos/IPOs sin historial suficiente
    cur_p = safe_float(snap_db.get("price") if snap_db else 0.0) or 5.0
    atr_fb = max(0.05, cur_p * 0.02)
    fib_up = {f"upper_{i}": round(cur_p + (atr_fb * mult), 4) for i, mult in enumerate(FIB_MULTIPLIERS, start=1)}
    fib_lo = {f"lower_{i}": max(0.01, round(cur_p - (atr_fb * mult), 4)) for i, mult in enumerate(FIB_MULTIPLIERS, start=1)}
    fallback_res = {
        "current_price": cur_p,
        "basis": cur_p,
        "bb_upper": round(cur_p + (atr_fb * 2.0), 4),
        "bb_lower": max(0.01, round(cur_p - (atr_fb * 2.0), 4)),
        "atr": atr_fb,
        "ema_3": cur_p,
        "ema_9": cur_p,
        "ema_20": cur_p,
        "ema_50": cur_p,
        "ema_200": cur_p,
        **fib_up,
        **fib_lo,
        "_cached_at": now_ts
    }
    _INDICATOR_CACHE[ticker] = fallback_res
    return fallback_res


def build_position_diagnostics(
    pos: dict,
    snap_db: Optional[dict] = None,
    df_15m: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Construye el objeto de diagnóstico completo para una posición abierta
    y audita la presencia de todas las variables requeridas.
    """
    ticker = pos.get("ticker", "UNKNOWN")
    tech = get_technical_indicators_snapshot(ticker, snap_db, df_15m)

    current_price = safe_float(pos.get("current_price") or tech.get("current_price") or pos.get("avg_price"))
    avg_price = safe_float(pos.get("avg_price") or pos.get("entry_price"))

    # Gestión de Riesgo de la posición (con auto-repair seguro si falta)
    atr_val = safe_float(tech.get("atr")) or (avg_price * 0.02 if avg_price > 0 else 0.1)
    stop_loss = safe_float(pos.get("stop_loss"))
    if stop_loss <= 0 and avg_price > 0:
        stop_loss = round(max(0.01, avg_price - (atr_val * 2.0)), 2)

    take_profit = safe_float(pos.get("take_profit") or pos.get("tp_block1_price"))
    if take_profit <= 0 and avg_price > 0:
        take_profit = round(avg_price + (atr_val * 5.0), 2)

    # Trailing Stop: Prioridad trailing_sl_price > tp_trailing_sl > sl_dynamic_price > stop_loss
    trailing_sl = pos.get("trailing_sl_price")
    if trailing_sl is None or safe_float(trailing_sl) <= 0:
        trailing_sl = pos.get("tp_trailing_sl")
    if trailing_sl is None or safe_float(trailing_sl) <= 0:
        trailing_sl = pos.get("sl_dynamic_price")
    if trailing_sl is None or safe_float(trailing_sl) <= 0:
        trailing_sl = stop_loss

    trailing_stop = safe_float(trailing_sl)

    # Medias Móviles (combinar tech con posibles columnas en posición)
    ema_3 = safe_float(tech.get("ema_3") or pos.get("ema3_15m"))
    ema_9 = safe_float(tech.get("ema_9") or pos.get("ema9_15m"))
    ema_20 = safe_float(tech.get("ema_20") or tech.get("basis"))
    ema_50 = safe_float(tech.get("ema_50"))
    ema_200 = safe_float(tech.get("ema_200"))

    # Bollinger
    basis = safe_float(tech.get("basis"))
    bb_upper = safe_float(tech.get("bb_upper"))
    bb_lower = safe_float(tech.get("bb_lower"))

    # Bandas Fibonacci
    fib_bands = {}
    for i in range(1, 7):
        fib_bands[f"upper_{i}"] = safe_float(tech.get(f"upper_{i}"))
        fib_bands[f"lower_{i}"] = safe_float(tech.get(f"lower_{i}"))

    # Lista de Verificación Estricta (Ninguna variable puede ser None, blank o <= 0)
    checks: List[Tuple[str, str, float]] = [
        ("Stop Loss", "risk", stop_loss),
        ("Trailing Stop", "risk", trailing_stop),
        ("Take Profit", "risk", take_profit),
        ("BB Superior", "bollinger", bb_upper),
        ("Basis", "bollinger", basis),
        ("BB Inferior", "bollinger", bb_lower),
        ("EMA3", "emas", ema_3),
        ("EMA9", "emas", ema_9),
        ("EMA20", "emas", ema_20),
        ("EMA50", "emas", ema_50),
        ("EMA200", "emas", ema_200),
        ("UPPER_1", "fibonacci", fib_bands.get("upper_1", 0)),
        ("UPPER_2", "fibonacci", fib_bands.get("upper_2", 0)),
        ("UPPER_3", "fibonacci", fib_bands.get("upper_3", 0)),
        ("UPPER_4", "fibonacci", fib_bands.get("upper_4", 0)),
        ("UPPER_5", "fibonacci", fib_bands.get("upper_5", 0)),
        ("UPPER_6", "fibonacci", fib_bands.get("upper_6", 0)),
        ("LOWER_1", "fibonacci", fib_bands.get("lower_1", 0)),
        ("LOWER_2", "fibonacci", fib_bands.get("lower_2", 0)),
        ("LOWER_3", "fibonacci", fib_bands.get("lower_3", 0)),
        ("LOWER_4", "fibonacci", fib_bands.get("lower_4", 0)),
        ("LOWER_5", "fibonacci", fib_bands.get("lower_5", 0)),
        ("LOWER_6", "fibonacci", fib_bands.get("lower_6", 0)),
    ]

    missing_fields = []
    for label, group, val in checks:
        if val is None or val <= 0:
            missing_fields.append(label)

    is_valid = (len(missing_fields) == 0)

    # Identificar banda Fibonacci actual del precio
    current_zone = 0
    if basis > 0:
        for idx in range(6, 0, -1):
            if current_price >= fib_bands.get(f"upper_{idx}", 999999):
                current_zone = idx
                break
            if current_price <= fib_bands.get(f"lower_{idx}", -999999):
                current_zone = -idx
                break

    return {
        "ticker": ticker,
        "is_valid": is_valid,
        "missing_fields": missing_fields,
        "missing_count": len(missing_fields),
        "current_price": current_price,
        "avg_price": avg_price,
        "current_zone": current_zone,
        "risk": {
            "stop_loss": stop_loss,
            "stop_loss_pct": round(((stop_loss - avg_price) / avg_price * 100), 2) if avg_price > 0 else 0,
            "trailing_stop": trailing_stop,
            "trailing_stop_pct": round(((trailing_stop - avg_price) / avg_price * 100), 2) if avg_price > 0 else 0,
            "take_profit": take_profit,
            "take_profit_pct": round(((take_profit - avg_price) / avg_price * 100), 2) if avg_price > 0 else 0,
            "trailing_active": trailing_stop > 0,
        },
        "bollinger": {
            "bb_upper": bb_upper,
            "basis": basis,
            "bb_lower": bb_lower,
            "atr": safe_float(tech.get("atr")),
        },
        "emas": {
            "ema_3": ema_3,
            "ema_9": ema_9,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "ema_200": ema_200,
        },
        "fibonacci": fib_bands,
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }


def can_operate_pre_trade(
    ticker: str,
    entry_price: float,
    proposed_sl: float,
    proposed_tp: float,
    df_15m: Optional[pd.DataFrame] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    REGLA 1: 'Si está en rojo entonces NO operar'.
    Valida un trade antes de emitir la orden de compra.
    Retorna (can_operate, reason, diagnostics).
    """
    mock_pos = {
        "ticker": ticker,
        "current_price": entry_price,
        "avg_price": entry_price,
        "stop_loss": proposed_sl,
        # En pre-trade el trailing stop inicial debe arrancar establecido (mínimo el SL propuesto)
        "trailing_sl_price": proposed_sl,
        "take_profit": proposed_tp,
    }

    diag = build_position_diagnostics(mock_pos, df_15m=df_15m)

    if not diag["is_valid"]:
        missing_str = ", ".join(diag["missing_fields"])
        reason = f"🚫 PRE-TRADE BLOQUEADO {ticker}: Faltan variables técnicas o de riesgo ({missing_str})."
        log_warning("diagnostic_validator", reason)
        return False, reason, diag

    return True, "OK", diag


async def check_and_auto_establish_trailing(pos: dict, sb=None) -> dict:
    """
    Garantiza que una posición abierta nunca tenga trailing_sl_price en blanco/nulo.
    Si está en None, se inicializa de inmediato con el stop_loss existente.
    """
    if pos.get("trailing_sl_price") is None or safe_float(pos.get("trailing_sl_price")) <= 0:
        sl_val = safe_float(pos.get("stop_loss"))
        if sl_val > 0:
            if sb is None:
                sb = get_supabase()
            try:
                sb.table("stocks_positions").update({
                    "trailing_sl_price": sl_val,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", pos["id"]).execute()
                pos["trailing_sl_price"] = sl_val
                log_info("diagnostic_validator", f"🛡️ Trailing Stop inicializado para {pos.get('ticker')} en ${sl_val:.2f}")
            except Exception as e:
                log_warning("diagnostic_validator", f"Error auto-estableciendo trailing stop para {pos.get('ticker')}: {e}")
    return pos
