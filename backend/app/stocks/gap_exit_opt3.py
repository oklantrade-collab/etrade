"""
eTrade v6.0 — GAP EXIT OPT3 (Opción 3 Optimizada: Tramos 25/50/25 + Gracia 10:15 ET)
====================================================================================
Modelo de salida para posiciones OPEN GAP UP / Alpha Runner, validado en backtest
de 8 semanas (scratch/run_entry_tsl_variants.py, variante E0_T0).

Activación: variable de entorno GAP_EXIT_MODEL=OPT3 (por defecto "LEGACY" => sin cambios).

Reglas (todas evaluadas con velas 15m CERRADAS, función sin estado):
  1. Stop Loss duro intrabarra: precio <= stop_loss  => cierre del remanente.
  2. Trailing Stop (TSL) al CIERRE de vela 15m: si Close <= TSL => cierre del remanente.
       TSL = Open + (Close-Open)/2 de la vela verde que perfora la Banda Bollinger Superior 15m
             (High > BB_sup y Close > Open), solo con velas que abren >= 30 min después de la
             vela de entrada (gracia de apertura: entrada 09:30 => TSL efectivo desde 10:15 ET).
  3. Tramo 1: 25% del tamaño original cuando RSI 1H >= 85 (una sola vez).
  4. Tramo 2: 50% del tamaño original en Clímax Macro: RSI 1H >= 90 y High 1H >= BB_sup 1H (una vez).
  5. Tramo 3: el 25% restante corre protegido por SL / Ratchet BE / EMA9 y TSL (cierre EOD lo maneja el monitor).
  6. Ratchet BE: con pico >= +4% el SL sube a entrada +1%. Trailing EMA9 15m: EMA9 ascendente => EMA9 - delta.

El RSI/BB de 1H se derivan de las velas 15m cerradas (sin lookahead), igual que en el backtest.
"""

import os
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from app.core.logger import log_info

MODULE = "GAP_EXIT_OPT3"

T1_PCT = 0.25
T2_PCT = 0.50
T1_RSI_1H = 85.0
T2_RSI_1H = 90.0
TSL_GRACE_MINUTES = 30      # velas elegibles: las que abren >= 30 min tras la vela de entrada
BE_TRIGGER_PCT = 4.0
BE_LOCK_MULT = 1.01
CANDLE_MINUTES = 15


def get_gap_exit_model() -> str:
    """Modelo de salida activo para posiciones GAP: 'OPT3' o 'LEGACY' (por defecto)."""
    return str(os.getenv("GAP_EXIT_MODEL", "LEGACY")).strip().upper()


def is_opt3_gap_position(position: Dict[str, Any]) -> bool:
    """True si el flag está en OPT3 y la posición es de tipo GAP (mismo criterio que stocks_adaptive_tp_v2)."""
    if get_gap_exit_model() != "OPT3":
        return False
    try:
        strat = str(position.get("strategy") or "")
        group_nm = str(position.get("group_name") or "")
        return ("GAP" in strat) or ("GAP" in group_nm) or int(position.get("reentry_count") or 0) > 0
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# Utilidades de indicadores (misma matemática que el backtest)
# ─────────────────────────────────────────────────────────────
def _col(df: pd.DataFrame, name: str) -> pd.Series:
    for c in (name, name.capitalize(), name.upper()):
        if c in df.columns:
            return df[c].astype(float)
    return pd.Series(dtype=float)


def _normalize(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if df is None or len(df) == 0:
        return None
    out = pd.DataFrame({
        "open": _col(df, "open"), "high": _col(df, "high"),
        "low": _col(df, "low"), "close": _col(df, "close"),
        "volume": _col(df, "volume") if len(_col(df, "volume")) else 0.0,
    }, index=df.index)
    return out.dropna(subset=["open", "high", "low", "close"])


def closed_candles(df: pd.DataFrame, now: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """Devuelve solo las velas 15m ya cerradas. Sin referencia de hora, asume que todas están cerradas."""
    if df is None or df.empty:
        return df
    idx = df.index
    if now is None and getattr(idx, "tz", None) is not None:
        now = pd.Timestamp.now(tz=idx.tz)
    if now is None:
        return df
    if getattr(idx, "tz", None) is not None and now.tzinfo is None:
        now = now.tz_localize(idx.tz)
    ends = idx + pd.Timedelta(minutes=CANDLE_MINUTES)
    return df[ends <= now]


def _bb_upper(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.Series:
    sma = close.rolling(period, min_periods=1).mean()
    std = close.rolling(period, min_periods=1).std().fillna(0.0)
    return sma + num_std * std


def _rsi_wilder(close: pd.Series, period: int = 14) -> float:
    """RSI de Wilder (idéntico a compute_rsi del motor GAP)."""
    from app.stocks.aduana_gap_runner_engine import compute_rsi
    if len(close) < 2:
        return 50.0
    return float(compute_rsi(close, period=min(period, len(close) - 1)).iloc[-1])


def live_1h_from_15m(df15: pd.DataFrame) -> pd.DataFrame:
    """Velas 1H (alineadas a 09:30) construidas solo con las 15m disponibles: sin lookahead."""
    return df15.resample("1h", offset="30min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()


def _entry_floor(position: Dict[str, Any], tz) -> Optional[pd.Timestamp]:
    raw = position.get("first_buy_at") or position.get("entry_time")
    if not raw:
        return None
    try:
        ts = pd.Timestamp(str(raw).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        if tz is not None:
            ts = ts.tz_convert(tz)
        else:
            ts = ts.tz_convert("America/New_York").tz_localize(None)
        return ts.floor(f"{CANDLE_MINUTES}min")
    except Exception:
        return None


def compute_tsl_15m(df15: pd.DataFrame, position: Dict[str, Any]) -> Dict[str, Any]:
    """
    TSL monotónico a partir de las velas 15m cerradas (sin estado persistido).
    Devuelve {'tsl_prev': TSL vigente ANTES de la última vela cerrada, 'tsl_now': incluyendo la última}.
    """
    out = {"tsl_prev": 0.0, "tsl_now": 0.0, "last_close": None}
    if df15 is None or len(df15) < 2:
        return out
    bbu = _bb_upper(df15["close"])
    ef = _entry_floor(position, df15.index.tz)
    if ef is not None:
        threshold = ef + pd.Timedelta(minutes=TSL_GRACE_MINUTES)
    else:
        last_day = df15.index[-1].normalize()
        threshold = last_day + pd.Timedelta(hours=10)
    tsl = 0.0
    tsl_before_last = 0.0
    n = len(df15)
    for i in range(n):
        if i == n - 1:
            tsl_before_last = tsl
        ts = df15.index[i]
        if ts < threshold:
            continue
        o, h, c = float(df15["open"].iloc[i]), float(df15["high"].iloc[i]), float(df15["close"].iloc[i])
        if c > o and h > float(bbu.iloc[i]):
            mid = round(o + (c - o) / 2.0, 2)
            if mid > tsl and mid < c:
                tsl = mid
    out.update({"tsl_prev": tsl_before_last, "tsl_now": tsl, "last_close": float(df15["close"].iloc[-1])})
    return out


# ─────────────────────────────────────────────────────────────
# Evaluador principal
# ─────────────────────────────────────────────────────────────
def evaluate_gap_opt3_exit(
    position: Dict[str, Any],
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    now: Optional[pd.Timestamp] = None,
) -> Dict[str, Any]:
    """
    Devuelve el mismo esquema que evaluate_gap_runner_aduana_exit, más:
      'tp_block': 'block1' | 'block2' | None   (columna tp_blockN_executed a marcar)
      'pct': porcentaje del tamaño original que se vende
    exit_type: 'none' | 'partial' | 'full' | 'trailing_update'
    """
    res: Dict[str, Any] = {
        "should_exit": False, "exit_type": "none", "action": "none", "rule_code": "", "reason": "",
        "shares_to_exit": 0, "pct": 0, "tp_block": None, "new_stop_loss": None,
        "rsi_1h": 50.0, "rsi_15m": 50.0, "model": "OPT3",
    }
    avg_price = float(position.get("avg_price") or position.get("entry_price") or current_price)
    shares0 = int(float(position.get("shares") or 0))
    rem_raw = position.get("shares_remaining")
    remaining = int(float(rem_raw)) if rem_raw not in (None, "") and float(rem_raw) > 0 else shares0
    cur_sl = float(position.get("stop_loss") or 0.0)
    if remaining <= 0 or avg_price <= 0:
        return res

    # 1) Stop Loss duro (intrabarra)
    if cur_sl > 0 and current_price <= cur_sl:
        is_be = cur_sl >= avg_price
        res.update({
            "should_exit": True, "exit_type": "full", "action": "sell",
            "rule_code": "ADUANA_GAP_BREAKEVEN_SL" if is_be else "ADUANA_GAP_HARD_SL",
            "shares_to_exit": remaining, "pct": 100,
            "reason": f"OPT3 Stop Loss: precio ${current_price:.2f} <= SL ${cur_sl:.2f}",
        })
        return res

    d15 = _normalize(df_15m)
    if d15 is None or len(d15) < 3:
        res["reason"] = "OPT3: datos 15m insuficientes"
        return res
    d15 = closed_candles(d15, now)
    if d15 is None or len(d15) < 3:
        res["reason"] = "OPT3: velas 15m cerradas insuficientes"
        return res

    last_close = float(d15["close"].iloc[-1])

    # 2) Trailing Stop al cierre de vela 15m (con gracia de apertura)
    tsl = compute_tsl_15m(d15, position)
    if tsl["tsl_prev"] > 0 and last_close <= tsl["tsl_prev"]:
        res.update({
            "should_exit": True, "exit_type": "full", "action": "sell",
            "rule_code": "ADUANA_GAP_OPT3_TSL_15M_CLOSE",
            "shares_to_exit": remaining, "pct": 100,
            "reason": f"OPT3 TSL 15m: Close ${last_close:.2f} <= TSL ${tsl['tsl_prev']:.2f} (50% de vela verde sobre BB sup.)",
        })
        return res

    # 3/4) Tramos por RSI 1H / Clímax Macro (1H derivada de las 15m cerradas)
    h1 = live_1h_from_15m(d15)
    rsi1h = _rsi_wilder(h1["close"]) if len(h1) >= 2 else 50.0
    res["rsi_1h"] = round(rsi1h, 1)
    bb1h_up = float(_bb_upper(h1["close"]).iloc[-1]) if len(h1) >= 1 else float("inf")
    h1_high = float(h1["high"].iloc[-1]) if len(h1) >= 1 else 0.0
    climax = (rsi1h >= T2_RSI_1H) and (h1_high >= bb1h_up)

    t1_done = bool(position.get("tp_block1_executed"))
    t2_done = bool(position.get("tp_block2_executed"))

    if (not t1_done) and rsi1h >= T1_RSI_1H:
        n = max(1, int(shares0 * T1_PCT))
        if remaining - n >= 1:
            res.update({
                "should_exit": True, "exit_type": "partial", "action": "sell",
                "rule_code": "ADUANA_GAP_OPT3_T1_25_RSI1H", "tp_block": "block1",
                "shares_to_exit": n, "pct": int(T1_PCT * 100),
                "reason": f"OPT3 Tramo 1 (25%): RSI 1H = {rsi1h:.1f} >= {T1_RSI_1H:.0f}",
            })
            return res
    if (not t2_done) and climax:
        n = max(1, int(shares0 * T2_PCT))
        if remaining - n >= 1:
            res.update({
                "should_exit": True, "exit_type": "partial", "action": "sell",
                "rule_code": "ADUANA_GAP_OPT3_T2_50_CLIMAX", "tp_block": "block2",
                "shares_to_exit": n, "pct": int(T2_PCT * 100),
                "reason": (f"OPT3 Tramo 2 (50%) Clímax Macro 1H: RSI 1H = {rsi1h:.1f} >= {T2_RSI_1H:.0f} "
                           f"y High 1H ${h1_high:.2f} >= BB sup. 1H ${bb1h_up:.2f}"),
            })
            return res

    # 5) Actualización de stops: Ratchet BE + trailing EMA9 15m
    best_sl, best_rule, best_reason = cur_sl, "", ""
    highest = float(position.get("highest_price_reached") or current_price)
    highest = max(highest, current_price)
    gain_peak = (highest - avg_price) / avg_price * 100.0
    if gain_peak >= BE_TRIGGER_PCT:
        be = round(avg_price * BE_LOCK_MULT, 2)
        if be > best_sl and be < current_price:
            best_sl, best_rule = be, "ADUANA_GAP_OPT3_BE_RATCHET"
            best_reason = f"OPT3 Ratchet BE: pico +{gain_peak:.1f}% >= +{BE_TRIGGER_PCT:.0f}% => SL entrada +1% (${be:.2f})"

    ema9 = d15["close"].ewm(span=9, adjust=False).mean()
    if len(ema9) >= 2 and float(ema9.iloc[-1]) > float(ema9.iloc[-2]):
        from app.stocks.aduana_gap_runner_engine import compute_atr
        atr = compute_atr(d15, 14) or last_close * 0.02
        prop = round(float(ema9.iloc[-1]) - max(0.01 * last_close, 0.5 * atr), 2)
        if prop > best_sl and prop < current_price:
            best_sl, best_rule = prop, "ADUANA_GAP_OPT3_EMA9_TRAIL"
            best_reason = f"OPT3 Trailing EMA9 15m ascendente: SL ${prop:.2f}"

    if best_rule and best_sl > cur_sl:
        res.update({"new_stop_loss": best_sl, "exit_type": "trailing_update",
                    "rule_code": best_rule, "reason": best_reason})
    return res


def log_legacy_shadow(position: Dict[str, Any], opt3_res: Dict[str, Any], legacy_res: Dict[str, Any]) -> None:
    """Registra qué habría hecho el modelo LEGACY (sin ejecutarlo) cuando OPT3 no actúa o actúa distinto."""
    try:
        if legacy_res and legacy_res.get("should_exit"):
            if (not opt3_res.get("should_exit")) or opt3_res.get("rule_code") != legacy_res.get("rule_code"):
                log_info(
                    MODULE,
                    f"[OPT3-SHADOW] {position.get('ticker')}: LEGACY habría ejecutado "
                    f"{legacy_res.get('rule_code')} ({legacy_res.get('exit_type')}, "
                    f"{legacy_res.get('shares_to_exit')} sh) | OPT3: "
                    f"{opt3_res.get('rule_code') or 'sin acción'}",
                )
    except Exception:
        pass
