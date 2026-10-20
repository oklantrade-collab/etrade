"""Motor de salidas (Exit Engine) para posiciones Paper Trading (Sprint 6).
Evalua de forma continua:
  1. Take Profit (+75% en long options / +60% del beneficio maximo en spreads).
  2. Stop Loss (-50% del debito o prima).
  3. Salida por tiempo (15 min antes de la campana en DTE, respetando early closes).
  4. Invalidacion de direccion APEX (direction flip).
  5. Cierre por datos degradados o stale.
Todas las salidas son validadas por ADUANA y simulan fills conservadores.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any, Optional
import pandas as pd

from app.core.logger import log_info, log_warning
from app.options import market_calendar as mc
from app.options import options_aduana as aduana
from app.options import paper_execution as pe
from app.strategy.panic_recovery_gate import calculate_fibonacci_bands
from app.options.aduana_gap_runner_options import compute_rsi, compute_bollinger_bands, _safe_col

MODULE = "OPTIONS_EXIT"

_TECH_CONTEXT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
TECH_CACHE_TTL = 45.0  # 45 segundos de cache en memoria por símbolo


def get_underlying_technical_context(symbol: str) -> dict[str, Any]:
    """
    Obtiene velas de 15m y 1h para el subyacente y calcula todos los indicadores
    requeridos para las salidas institucionales y trailing stops de opciones.
    """
    sym = symbol.strip().upper()
    now_ts = time.time()
    if sym in _TECH_CONTEXT_CACHE:
        cached_ts, cached_data = _TECH_CONTEXT_CACHE[sym]
        if now_ts - cached_ts < TECH_CACHE_TTL:
            return cached_data

    res: dict[str, Any] = {"valid": False, "symbol": sym}
    try:
        import yfinance as yf
        t = yf.Ticker(sym)
        df_15m = t.history(period="5d", interval="15m")
        df_1h = t.history(period="1mo", interval="1h")

        if df_15m is None or df_15m.empty or len(df_15m) < 10:
            return res

        c15 = _safe_col(df_15m, "close")
        cur_p = float(c15.iloc[-1])
        res["current_price"] = cur_p

        # 1. Indicadores en 15 Minutos (EMA3, EMA9, Fib Bands, Bollinger, Vela Cerrada, SIPV Clímax)
        o15 = _safe_col(df_15m, "open")
        h15 = _safe_col(df_15m, "high")
        l15 = _safe_col(df_15m, "low")

        ema3_15m_s = c15.ewm(span=3, adjust=False).mean()
        ema9_15m_s = c15.ewm(span=9, adjust=False).mean()
        res["ema3_15m"] = float(ema3_15m_s.iloc[-1])
        res["ema9_15m"] = float(ema9_15m_s.iloc[-1])
        res["prev_ema9_15m"] = float(ema9_15m_s.iloc[-2]) if len(ema9_15m_s) >= 2 else res["ema9_15m"]

        fib_15m = calculate_fibonacci_bands(df_15m, cur_p)
        res["upper_6_15m"] = float(fib_15m.get("upper_6") or 0.0)
        res["lower_6_15m"] = float(fib_15m.get("lower_6") or 0.0)
        res["bb_upper_15m"] = float(fib_15m.get("upper_band") or 0.0)
        res["bb_lower_15m"] = float(fib_15m.get("lower_band") or 0.0)
        res["atr_15m"] = float(fib_15m.get("atr") or (cur_p * 0.005))

        # Vela cerrada de 15m (para Trailing Stop y SIPV Clímax de 15m)
        idx_closed_15m = -2 if len(df_15m) >= 2 else -1
        h_closed_15m = float(h15.iloc[idx_closed_15m])
        l_closed_15m = float(l15.iloc[idx_closed_15m])
        o_closed_15m = float(o15.iloc[idx_closed_15m])
        c_closed_15m = float(c15.iloc[idx_closed_15m])

        res["candle_closed_high_15m"] = h_closed_15m
        res["candle_closed_low_15m"] = l_closed_15m
        res["candle_closed_open_15m"] = o_closed_15m
        res["candle_closed_close_15m"] = c_closed_15m

        # SIPV Clímax 15m con filtro Bollinger:
        # CALLs: High > BB_Upper (15m) y mecha superior >= 40% (o vela roja con mecha >= 30%)
        rng_closed_15m = max(1e-4, h_closed_15m - l_closed_15m)
        u_wick_15m = max(0.0, h_closed_15m - max(o_closed_15m, c_closed_15m))
        l_wick_15m = max(0.0, min(o_closed_15m, c_closed_15m) - l_closed_15m)
        bb_u_15m = res["bb_upper_15m"]
        bb_l_15m = res["bb_lower_15m"]

        res["is_sipv_sell_15m"] = (bb_u_15m > 0 and h_closed_15m > bb_u_15m) and (
            (u_wick_15m / rng_closed_15m >= 0.40) or (c_closed_15m < o_closed_15m and (u_wick_15m / rng_closed_15m >= 0.30))
        )
        res["is_sipv_buy_15m"] = (bb_l_15m > 0 and l_closed_15m < bb_l_15m) and (
            (l_wick_15m / rng_closed_15m >= 0.40) or (c_closed_15m > o_closed_15m and (l_wick_15m / rng_closed_15m >= 0.30))
        )

        # 2. Indicadores en 1 Hora (EMA3 Slope, RSI 14, Bollinger, Fib Bands, SIPV)
        if df_1h is not None and not df_1h.empty and len(df_1h) >= 10:
            c1h = _safe_col(df_1h, "close")
            o1h = _safe_col(df_1h, "open")
            h1h = _safe_col(df_1h, "high")
            l1h = _safe_col(df_1h, "low")

            ema3_1h_s = c1h.ewm(span=3, adjust=False).mean()
            cur_ema3_1h = float(ema3_1h_s.iloc[-1])
            prev_ema3_1h = float(ema3_1h_s.iloc[-2]) if len(ema3_1h_s) >= 2 else cur_ema3_1h
            res["ema3_1h"] = cur_ema3_1h
            res["ema3_slope_1h"] = (cur_ema3_1h - prev_ema3_1h) / (prev_ema3_1h + 1e-6) * 100.0

            rsi_1h_s = compute_rsi(c1h, period=14)
            res["rsi_1h"] = float(rsi_1h_s.iloc[-1])

            fib_1h = calculate_fibonacci_bands(df_1h, cur_p)
            res["upper_6_1h"] = float(fib_1h.get("upper_6") or 0.0)
            res["lower_6_1h"] = float(fib_1h.get("lower_6") or 0.0)
            res["bb_upper_1h"] = float(fib_1h.get("upper_band") or 0.0)
            res["bb_lower_1h"] = float(fib_1h.get("lower_band") or 0.0)

            # Velas de 1H: tanto la vela cerrada anterior como la actual
            res["candle_high_1h"] = float(h1h.iloc[-1])
            res["candle_low_1h"] = float(l1h.iloc[-1])
            res["candle_open_1h"] = float(o1h.iloc[-1])
            res["candle_close_1h"] = float(c1h.iloc[-1])

            # Vela cerrada anterior de 1H (para evaluar Trailing Stop al cierre de 1H)
            idx_closed = -2 if len(df_1h) >= 2 else -1
            h_closed = float(h1h.iloc[idx_closed])
            l_closed = float(l1h.iloc[idx_closed])
            o_closed = float(o1h.iloc[idx_closed])
            c_closed = float(c1h.iloc[idx_closed])

            res["candle_closed_high_1h"] = h_closed
            res["candle_closed_low_1h"] = l_closed
            res["candle_closed_open_1h"] = o_closed
            res["candle_closed_close_1h"] = c_closed

            # Detección de Mechas SIPV sobre vela cerrada de 1H
            rng_closed = max(1e-4, h_closed - l_closed)
            u_wick = max(0.0, h_closed - max(o_closed, c_closed))
            l_wick = max(0.0, min(o_closed, c_closed) - l_closed)
            res["is_sipv_sell"] = (u_wick / rng_closed >= 0.40) or (c_closed < o_closed and (u_wick / rng_closed >= 0.30))
            res["is_sipv_buy"] = (l_wick / rng_closed >= 0.40) and (c_closed >= o_closed)
            res["is_sipv_sell_1h"] = res["is_sipv_sell"]
            res["is_sipv_buy_1h"] = res["is_sipv_buy"]

        res["valid"] = True
        _TECH_CONTEXT_CACHE[sym] = (now_ts, res)
        return res
    except Exception as e:
        log_warning(MODULE, f"Error calculando contexto técnico para {sym}: {e}")
        return res


DB_EXIT_REASONS_MAP = {
    "take_profit": "take_profit",
    "stop_loss": "stop_loss",
    "forced_close_time": "forced_close_time",
    "signal_invalidation": "signal_invalidation",
    "bad_data_close": "bad_data_close",
    "manual_simulated": "manual_simulated",
    "tp_rsi_climax_1h": "take_profit",
    "tp_upper_6": "take_profit",
    "tp_lower_6": "take_profit",
    "sl_underlying_pierced": "stop_loss",
    "ema_cross_15m": "stop_loss",
    "ema3_flat_descending_1h": "signal_invalidation",
    "ema3_flat_ascending_1h": "signal_invalidation",
    "sipv_trend_flip_1h": "signal_invalidation",
    "sipv_trend_flip_15m": "signal_invalidation",
}


def evaluate_technical_rules_and_stops(
    position: dict[str, Any],
    tech: dict[str, Any],
    now_dt: datetime
) -> tuple[bool, str | None, dict[str, Any]]:
    """
    Evalúa las 5 reglas de salida institucional y la actualización monotónica
    del Stop Loss (EMA9 15m) y Trailing Stop (Midpoint 15m) para CALLs y PUTs.
    """
    if not tech or not tech.get("valid"):
        return False, None, {}

    stype = str(position.get("strategy_type") or "").lower()
    direction = str(position.get("direction") or "").lower()
    is_call = ("call" in stype) or (direction in ("bullish", "call"))
    is_put = ("put" in stype) or (direction in ("bearish", "put"))

    current_price = float(tech.get("current_price") or 0.0)
    if current_price <= 0:
        return False, None, {}

    exit_plan = dict(position.get("exit_plan") or {})
    current_sl = float(exit_plan.get("stop_loss_underlying") or 0.0)
    current_sl_type = str(exit_plan.get("trailing_sl_type") or "INITIAL")

    # ─────────────────────────────────────────────────────────────
    # FASE 1: ACTUALIZACIÓN MONOTÓNICA DE STOP LOSS & TRAILING STOP
    # ─────────────────────────────────────────────────────────────
    cur_ema9_15m = float(tech.get("ema9_15m") or 0.0)
    prev_ema9_15m = float(tech.get("prev_ema9_15m") or cur_ema9_15m)
    atr_15m = float(tech.get("atr_15m") or (current_price * 0.005))
    delta_sl = max(0.15 * atr_15m, 0.0020 * current_price)

    new_sl = current_sl
    new_sl_type = current_sl_type

    if is_call:
        # En CALL: Si EMA9 sube, elevar SL dinámico
        if cur_ema9_15m > prev_ema9_15m and cur_ema9_15m > 0:
            proposed_sl = round(cur_ema9_15m - delta_sl, 2)
            if proposed_sl > new_sl:
                new_sl = proposed_sl
                new_sl_type = "EMA9_15M"

        # Trailing Stop 15m Midpoint (si High > BB_Upper 15m y vela verde: Close > Open)
        bb_upper_15m = float(tech.get("bb_upper_15m") or 0.0)
        h_15m = float(tech.get("candle_closed_high_15m") or 0.0)
        l_15m = float(tech.get("candle_closed_low_15m") or 0.0)
        c_15m = float(tech.get("candle_closed_close_15m") or 0.0)
        o_15m = float(tech.get("candle_closed_open_15m") or 0.0)

        if bb_upper_15m > 0 and h_15m > bb_upper_15m and c_15m > o_15m:
            midpoint_15m = round((h_15m + l_15m) / 2.0, 2)
            if midpoint_15m > new_sl:
                new_sl = midpoint_15m
                new_sl_type = "MIDPOINT_15M"

    elif is_put:
        # En PUT: Si EMA9 baja, reducir techo de SL dinámico
        if cur_ema9_15m < prev_ema9_15m and cur_ema9_15m > 0:
            proposed_sl = round(cur_ema9_15m + delta_sl, 2)
            if new_sl == 0.0 or proposed_sl < new_sl:
                new_sl = proposed_sl
                new_sl_type = "EMA9_15M"

        # Trailing Stop 15m Midpoint para PUTs (si Low < BB_Lower 15m y vela roja: Close < Open)
        bb_lower_15m = float(tech.get("bb_lower_15m") or 0.0)
        h_15m = float(tech.get("candle_closed_high_15m") or 0.0)
        l_15m = float(tech.get("candle_closed_low_15m") or 0.0)
        c_15m = float(tech.get("candle_closed_close_15m") or 0.0)
        o_15m = float(tech.get("candle_closed_open_15m") or 0.0)

        if bb_lower_15m > 0 and l_15m < bb_lower_15m and c_15m < o_15m:
            midpoint_15m = round((h_15m + l_15m) / 2.0, 2)
            if new_sl == 0.0 or midpoint_15m < new_sl:
                new_sl = midpoint_15m
                new_sl_type = "MIDPOINT_15M"

    exit_plan["stop_loss_underlying"] = new_sl
    exit_plan["trailing_sl_type"] = new_sl_type
    exit_plan["last_underlying_price"] = current_price
    exit_plan["last_eval_at"] = now_dt.isoformat()

    # ─────────────────────────────────────────────────────────────
    # FASE 2: VERIFICAR SI EL STOP LOSS DEL SUBYACENTE FUE PERFORADO
    # ─────────────────────────────────────────────────────────────
    if is_call and new_sl > 0.0 and current_price <= new_sl:
        return True, "sl_underlying_pierced", {
            "detail": f"Stop Loss Técnico en Subyacente perforado: ${current_price:.2f} <= SL ${new_sl:.2f} ({new_sl_type})",
            "exit_plan": exit_plan
        }
    elif is_put and new_sl > 0.0 and current_price >= new_sl:
        return True, "sl_underlying_pierced", {
            "detail": f"Stop Loss Técnico en Subyacente perforado: ${current_price:.2f} >= SL ${new_sl:.2f} ({new_sl_type})",
            "exit_plan": exit_plan
        }

    # ─────────────────────────────────────────────────────────────
    # FASE 3: EVALUACIÓN DE LAS 5 CONDICIONES INSTITUCIONALES
    # ─────────────────────────────────────────────────────────────
    ema3_15m = float(tech.get("ema3_15m") or 0.0)
    ema9_15m = float(tech.get("ema9_15m") or 0.0)
    rsi_1h = float(tech.get("rsi_1h") or 50.0)
    upper_6_15m = float(tech.get("upper_6_15m") or 0.0)
    upper_6_1h = float(tech.get("upper_6_1h") or 0.0)
    lower_6_15m = float(tech.get("lower_6_15m") or 0.0)
    lower_6_1h = float(tech.get("lower_6_1h") or 0.0)
    ema3_slope_1h = float(tech.get("ema3_slope_1h") or 0.0)
    is_sipv_sell_15m = bool(tech.get("is_sipv_sell_15m", False))
    is_sipv_buy_15m = bool(tech.get("is_sipv_buy_15m", False))
    is_sipv_sell_1h = bool(tech.get("is_sipv_sell_1h", tech.get("is_sipv_sell", False)))
    is_sipv_buy_1h = bool(tech.get("is_sipv_buy_1h", tech.get("is_sipv_buy", False)))

    if is_call:
        # Regla 1: EMA3 < EMA9 en 15m
        if ema3_15m > 0 and ema9_15m > 0 and ema3_15m < ema9_15m:
            return True, "ema_cross_15m", {
                "detail": f"Cierre de CALL: EMA3 15m (${ema3_15m:.2f}) < EMA9 15m (${ema9_15m:.2f})",
                "exit_plan": exit_plan
            }

        # Regla 2: RSI 1H >= 80
        if rsi_1h >= 80.0:
            return True, "tp_rsi_climax_1h", {
                "detail": f"Take Profit CALL Clímax: RSI 1H ({rsi_1h:.1f}) >= 80.0",
                "exit_plan": exit_plan
            }

        # Regla 3: Toca UPPER_6 en 15m o 1H
        if (upper_6_15m > 0 and current_price >= upper_6_15m) or (upper_6_1h > 0 and current_price >= upper_6_1h):
            hit_level = upper_6_15m if current_price >= upper_6_15m else upper_6_1h
            return True, "tp_upper_6", {
                "detail": f"Take Profit CALL: Subyacente (${current_price:.2f}) alcanzó UPPER_6 (${hit_level:.2f})",
                "exit_plan": exit_plan
            }

        # Regla 4: Ángulo de EMA3 en 1H lateral o descendente (slope <= 0)
        if ema3_slope_1h <= 0.0:
            return True, "ema3_flat_descending_1h", {
                "detail": f"Cierre defensivo CALL: Ángulo EMA3 1H plano o descendente ({ema3_slope_1h:+.4f}%)",
                "exit_plan": exit_plan
            }

        # Regla 5: SIPV Clímax 15m (o confirmación en 1H)
        if is_sipv_sell_15m:
            return True, "sipv_trend_flip_15m", {
                "detail": "Cierre de CALL: SIPV Clímax 15m (High > Banda Bollinger Superior con mecha de rechazo)",
                "exit_plan": exit_plan
            }
        elif is_sipv_sell_1h:
            return True, "sipv_trend_flip_1h", {
                "detail": "Cierre de CALL: SIPV marca SELL / Rechazo institucional en techo 1H",
                "exit_plan": exit_plan
            }

    elif is_put:
        # Regla 1 (Inversa): EMA3 > EMA9 en 15m
        if ema3_15m > 0 and ema9_15m > 0 and ema3_15m > ema9_15m:
            return True, "ema_cross_15m", {
                "detail": f"Cierre de PUT: EMA3 15m (${ema3_15m:.2f}) > EMA9 15m (${ema9_15m:.2f})",
                "exit_plan": exit_plan
            }

        # Regla 2 (Inversa): RSI 1H <= 20
        if rsi_1h <= 20.0:
            return True, "tp_rsi_climax_1h", {
                "detail": f"Take Profit PUT Clímax: RSI 1H ({rsi_1h:.1f}) <= 20.0",
                "exit_plan": exit_plan
            }

        # Regla 3 (Inversa): Toca LOWER_6 en 15m o 1H
        if (lower_6_15m > 0 and current_price <= lower_6_15m) or (lower_6_1h > 0 and current_price <= lower_6_1h):
            hit_level = lower_6_15m if current_price <= lower_6_15m else lower_6_1h
            return True, "tp_lower_6", {
                "detail": f"Take Profit PUT: Subyacente (${current_price:.2f}) alcanzó LOWER_6 (${hit_level:.2f})",
                "exit_plan": exit_plan
            }

        # Regla 4 (Inversa): Ángulo de EMA3 en 1H lateral o ascendente (slope >= 0)
        if ema3_slope_1h >= 0.0:
            return True, "ema3_flat_ascending_1h", {
                "detail": f"Cierre defensivo PUT: Ángulo EMA3 1H plano o ascendente ({ema3_slope_1h:+.4f}%)",
                "exit_plan": exit_plan
            }

        # Regla 5 (Inversa): SIPV Clímax 15m (o confirmación en 1H)
        if is_sipv_buy_15m:
            return True, "sipv_trend_flip_15m", {
                "detail": "Cierre de PUT: SIPV Clímax 15m (Low < Banda Bollinger Inferior con mecha de absorción)",
                "exit_plan": exit_plan
            }
        elif is_sipv_buy_1h:
            return True, "sipv_trend_flip_1h", {
                "detail": "Cierre de PUT: SIPV marca BUY / Absorción institucional en suelo 1H",
                "exit_plan": exit_plan
            }



    return False, None, {"exit_plan": exit_plan}


def should_exit_take_profit(position: dict[str, Any], unrealized_pnl: float, eff: dict[str, Any]) -> tuple[bool, str | None]:
    """Evalua condicion de Take Profit (§12.3)."""
    stype = position.get("strategy_type") or ""
    invested = float(position.get("entry_total_invested") or 0.0)
    max_profit = position.get("max_profit_total")

    if stype in ("long_call", "long_put"):
        tp_pct = float(eff.get("long_tp_pct") or 75.0)
        target = invested * (tp_pct / 100.0)
        if unrealized_pnl >= target and target > 0:
            return True, f"Take Profit alcanzado: +${unrealized_pnl:.2f} >= +${target:.2f} (+{tp_pct}%)"
    else:
        # Spreads: 60% del beneficio maximo
        tp_pct = float(eff.get("spread_tp_pct") or 60.0)
        if max_profit and max_profit > 0:
            target = float(max_profit) * (tp_pct / 100.0)
            if unrealized_pnl >= target:
                return True, f"Take Profit alcanzado: +${unrealized_pnl:.2f} >= +${target:.2f} (+{tp_pct}% de benef. max)"
        elif invested > 0:
            target = invested * (tp_pct / 100.0)
            if unrealized_pnl >= target:
                return True, f"Take Profit alcanzado: +${unrealized_pnl:.2f} >= +${target:.2f}"

    return False, None


def should_exit_stop_loss(position: dict[str, Any], unrealized_pnl: float, eff: dict[str, Any]) -> tuple[bool, str | None]:
    """Evalua condicion de Stop Loss simulado (§12.3)."""
    stype = position.get("strategy_type") or ""
    invested = float(position.get("entry_total_invested") or 0.0)

    if stype in ("long_call", "long_put"):
        sl_pct = float(eff.get("long_sl_pct") or 50.0)
    else:
        sl_pct = float(eff.get("spread_sl_pct") or 50.0)

    stop_threshold = -invested * (sl_pct / 100.0)
    if unrealized_pnl <= stop_threshold and invested > 0:
        return True, f"Stop Loss alcanzado: ${unrealized_pnl:.2f} <= -${abs(stop_threshold):.2f} (-{sl_pct}%)"

    return False, None


def should_exit_by_time(position: dict[str, Any], now: datetime, eff: dict[str, Any]) -> tuple[bool, str | None]:
    """Cierre forzado antes de la campana en la fecha de expiracion (§12.3)."""
    expiry_str = str(position.get("expiry") or "")[:10]
    if not expiry_str:
        return False, None

    expiry_date = date.fromisoformat(expiry_str)
    now_date = mc.to_ny(now).date()

    if now_date == expiry_date:
        buffer_min = int(eff.get("force_close_minutes_before") or 15)
        force_time = mc.force_close_time(now, buffer_min)
        if now >= force_time:
            return True, f"Cierre forzado por tiempo: vencimiento hoy y hora actual supera {force_time.strftime('%H:%M %Z')}"

    return False, None


def should_exit_by_invalidation(position: dict[str, Any], underlying: dict[str, Any], eff: dict[str, Any]) -> tuple[bool, str | None]:
    """Invalidacion por inversion de senal APEX o datos corruptos (§12.3)."""
    if not eff.get("exit_on_direction_flip", True):
        return False, None

    pos_dir = position.get("direction")
    und_dir = underlying.get("direction")
    if pos_dir and und_dir and pos_dir != und_dir:
        return True, f"Senal APEX invertida: posicion '{pos_dir}' vs nueva direccion '{und_dir}'"

    return False, None


def evaluate_position_exit(position: dict[str, Any],
                           quotes_by_contract: dict[int, dict[str, Any]] | None,
                           underlying: dict[str, Any],
                           eff: dict[str, Any],
                           now: datetime | None = None,
                           tech_context: dict[str, Any] | None = None) -> tuple[bool, str | None, dict[str, Any]]:
    """Evalua si una posicion debe cerrarse y bajo que motivo."""
    now_dt = now or datetime.now(timezone.utc)

    # 1. Mark to market
    mark = pe.mark_position_to_market(position, quotes_by_contract, eff)
    unrealized_pnl = mark["unrealized_pnl"]

    # 2. Cierre forzado por tiempo (maxima prioridad para evitar ejercicio/asignacion)
    by_time, reason_time = should_exit_by_time(position, now_dt, eff)
    if by_time:
        return True, "forced_close_time", {"detail": reason_time, "mark": mark}

    # 3. Stop Loss en prima (-50%)
    by_sl, reason_sl = should_exit_stop_loss(position, unrealized_pnl, eff)
    if by_sl:
        return True, "stop_loss", {"detail": reason_sl, "mark": mark}

    # 4. Take Profit en prima (+75% / +60%)
    by_tp, reason_tp = should_exit_take_profit(position, unrealized_pnl, eff)
    if by_tp:
        return True, "take_profit", {"detail": reason_tp, "mark": mark}

    # 5. Evaluación Técnica Avanzada en Subyacente (CALLs y PUTs)
    # Reglas 1-5 institucionales y Stop Loss/Trailing Stop técnico
    exit_plan_updated = None
    if tech_context and tech_context.get("valid"):
        by_tech, reason_tech, tech_info = evaluate_technical_rules_and_stops(position, tech_context, now_dt)
        exit_plan_updated = tech_info.get("exit_plan")
        if by_tech:
            return True, reason_tech, {"detail": tech_info.get("detail"), "mark": mark, "exit_plan": exit_plan_updated}

    # 6. Invalidacion de senal APEX
    by_inv, reason_inv = should_exit_by_invalidation(position, underlying, eff)
    if by_inv:
        return True, "signal_invalidation", {"detail": reason_inv, "mark": mark, "exit_plan": exit_plan_updated}

    return False, None, {"mark": mark, "exit_plan": exit_plan_updated}


def process_open_positions(sb, eff: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Recorre todas las posiciones abiertas, actualiza su mark-to-market y ejecuta salidas aprobadas."""
    now_dt = now or datetime.now(timezone.utc)
    try:
        positions = sb.table("opt_paper_trades").select("*").eq("status", "open").execute().data or []
    except Exception as e:
        log_warning(MODULE, f"Error al cargar posiciones: {e}")
        return {"open_count": 0, "closed_count": 0, "error": str(e)}

    if not positions:
        return {"open_count": 0, "closed_count": 0, "exits": []}

    # Cargar subyacentes y ultimas cotizaciones
    uids = list(set(p["underlying_id"] for p in positions if p.get("underlying_id")))
    und_rows = sb.table("opt_underlyings").select("*").in_("id", uids).execute().data or [] if uids else []
    und_map = {u["id"]: u for u in und_rows}

    # Cotizaciones recientes y mapeo por conid y contract_id
    contracts_rows = sb.table("opt_contracts").select("id, conid").execute().data or []
    conid_by_cid = {c["id"]: c.get("conid") for c in contracts_rows}
    cid_by_conid = {c["conid"]: c["id"] for c in contracts_rows if c.get("conid")}

    quotes_rows = sb.table("opt_quotes_latest").select("*").execute().data or []
    quotes_map: dict[Any, dict[str, Any]] = {}
    for q in quotes_rows:
        cid = q.get("contract_id")
        if cid:
            quotes_map[cid] = q
            conid = conid_by_cid.get(cid)
            if conid:
                quotes_map[conid] = q

    # Cargar contexto técnico de 15m y 1H para cada símbolo de subyacente
    symbols = list(set(p["symbol"] for p in positions if p.get("symbol")))
    tech_map: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        try:
            tech_map[sym] = get_underlying_technical_context(sym)
        except Exception as e_tech:
            log_warning(MODULE, f"Error obteniendo contexto técnico para {sym}: {e_tech}")
            tech_map[sym] = {}

    closed_count = 0
    exits_summary: list[dict[str, Any]] = []

    for pos in positions:
        pid = pos["id"]
        und = und_map.get(pos.get("underlying_id")) or {}
        tech_ctx = tech_map.get(pos.get("symbol") or "")
        should_exit, reason, info = evaluate_position_exit(pos, quotes_map, und, eff, now_dt, tech_context=tech_ctx)

        mark = info.get("mark") or {}
        if should_exit and reason:
            # Validar con ADUANA de salida
            aduana_res = aduana.validate_exit(
                reason,
                aduana.AduanaContext(
                    now=now_dt,
                    underlying_id=pos.get("underlying_id") or 1,
                    execution_mode=eff.get("execution_mode", "paper"),
                )
            )

            # Simular fill de salida (si es stop_loss o forzado, aplica slippage adverso)
            adverse = reason in ("stop_loss", "forced_close_time", "sl_underlying_pierced")
            exit_fill_res = pe.simulate_exit_fill(pos, quotes_map, eff, reason, adverse=adverse, now=now_dt)

            db_exit_reason = DB_EXIT_REASONS_MAP.get(reason, "signal_invalidation" if "flip" in reason or "cross" in reason else ("take_profit" if "tp" in reason else "stop_loss"))
            active_plan = dict(info.get("exit_plan") or pos.get("exit_plan") or {})
            active_plan["detailed_exit_reason"] = reason
            active_plan["detailed_exit_text"] = info.get("detail", reason)

            # Actualizar posicion como cerrada
            upd = {
                "status": "closed",
                "exit_time": exit_fill_res.exit_time,
                "exit_credit": exit_fill_res.exit_credit,
                "exit_fills": exit_fill_res.exit_fills,
                "exit_costs": exit_fill_res.exit_costs,
                "exit_total_recovered": exit_fill_res.exit_total_recovered,
                "realized_pnl": exit_fill_res.realized_pnl,
                "unrealized_pnl": 0.0,
                "last_mark_price": exit_fill_res.exit_credit,
                "last_mark_at": now_dt.isoformat(),
                "exit_reason": db_exit_reason,
                "exit_plan": active_plan,
                "updated_at": now_dt.isoformat(),
            }
            sb.table("opt_paper_trades").update(upd).eq("id", pid).execute()

            # Registrar evento de riesgo
            event_type = "forced_close" if reason == "forced_close_time" else ("signal_flip" if reason == "signal_invalidation" else "stop_approaching")
            try:
                sb.table("opt_risk_events").insert({
                    "paper_trade_id": pid,
                    "event_type": event_type,
                    "details": {
                        "exit_reason": reason,
                        "realized_pnl": exit_fill_res.realized_pnl,
                        "aduana_approval": aduana_res.approved,
                        "info": info.get("detail"),
                    },
                    "created_at": now_dt.isoformat(),
                }).execute()
            except Exception as exc:
                log_warning(MODULE, f"Aviso al registrar risk_event: {exc}")

            closed_count += 1
            exits_summary.append({"position_id": pid, "symbol": pos["symbol"], "reason": reason, "realized_pnl": exit_fill_res.realized_pnl})
            log_info(MODULE, f"Posicion {pid} ({pos['symbol']}) cerrada por {reason}: PnL=${exit_fill_res.realized_pnl:.2f}")
        else:
            # Solo actualizar mark to market y persistir nuevo exit_plan
            upd_payload: dict[str, Any] = {
                "unrealized_pnl": mark.get("unrealized_pnl", 0.0),
                "last_mark_price": mark.get("last_mark_price", 0.0),
                "last_mark_at": now_dt.isoformat(),
                "updated_at": now_dt.isoformat(),
            }
            active_exit_plan = (info.get("exit_plan") or mark.get("exit_plan"))
            if active_exit_plan:
                upd_payload["exit_plan"] = active_exit_plan
            sb.table("opt_paper_trades").update(upd_payload).eq("id", pid).execute()

    return {
        "open_count": len(positions) - closed_count,
        "closed_count": closed_count,
        "exits": exits_summary,
    }
