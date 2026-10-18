"""Motor Central de Catalizadores para Opciones (CALL/PUT) y Stocks.
Ejecuta la evaluacion de los 4 catalizadores sobre velas cerradas y resuelve el arbitraje.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional
import pandas as pd

from app.options.catalysts.indicators import (
    calculate_adx_wilder,
    calculate_atr,
    calculate_fibonacci_basis,
    calculate_sipv_delta_buffer,
    _safe_series,
)
from app.options.catalysts.arbitration import (
    CatalystComponent,
    ArbitrationResolution,
    resolve_arbitration,
)


def evaluate_c1_gap_and_go(
    df_5m: pd.DataFrame,
    prev_close: float,
    atr_1d: float,
    cfg: dict[str, Any],
) -> CatalystComponent:
    """C1: Open Gap Up & Down (5m) bajo modelo Gap&Go.
    - Requiere que la 1ra o 2da vela de 5m confirme el sentido.
    - Se suspende el bloqueo anti-climax durante la primera vela.
    """
    if df_5m is None or len(df_5m) < 1 or prev_close <= 0 or atr_1d <= 0:
        return CatalystComponent("gap_go", None, 0.0, False, {"reason": "Datos insuficientes"})

    open_candle_1 = float(_safe_series(df_5m, "open").iloc[0])
    raw_gap_pct = (open_candle_1 - prev_close) / prev_close * 100.0
    gap_atr = (open_candle_1 - prev_close) / atr_1d

    min_gap_atr = float(cfg.get("gate_gap_min_atr") or 0.5)
    max_gap_atr = float(cfg.get("gate_gap_max_atr") or 3.0)

    # Evaluar si tenemos 2da vela para confirmacion de continuacion
    has_two_candles = len(df_5m) >= 2
    c1 = df_5m.iloc[0]
    c1_open = float(_safe_series(df_5m, "open").iloc[0])
    c1_close = float(_safe_series(df_5m, "close").iloc[0])
    c1_green = c1_close >= c1_open
    c1_red = c1_close < c1_open

    # En caso de Gap Up (Alcista / CALL)
    if gap_atr >= min_gap_atr:
        if gap_atr > max_gap_atr:
            return CatalystComponent("gap_go", None, 0.0, False, {
                "reason": f"Gap Up excesivo ({gap_atr:.1f} ATR > {max_gap_atr:.1f} ATR): riesgo de agotamiento",
                "gap_atr": round(gap_atr, 2), "gap_pct": round(raw_gap_pct, 2),
            })

        # Confirmacion: si hay 2da vela, que la tendencia continue
        if has_two_candles:
            c2_close = float(_safe_series(df_5m, "close").iloc[1])
            is_confirmed = c2_close >= c1_open
        else:
            is_confirmed = c1_green

        if is_confirmed:
            return CatalystComponent("gap_go", "bullish", 30.0, True, {
                "gap_atr": round(gap_atr, 2), "gap_pct": round(raw_gap_pct, 2),
                "confirmed": True, "candles_checked": len(df_5m),
            })

    # En caso de Gap Down (Bajista / PUT)
    elif gap_atr <= -min_gap_atr:
        abs_gap_atr = abs(gap_atr)
        if abs_gap_atr > max_gap_atr:
            return CatalystComponent("gap_go", None, 0.0, False, {
                "reason": f"Gap Down excesivo ({abs_gap_atr:.1f} ATR > {max_gap_atr:.1f} ATR): capitulacion extrema",
                "gap_atr": round(gap_atr, 2), "gap_pct": round(raw_gap_pct, 2),
            })

        if has_two_candles:
            c2_close = float(_safe_series(df_5m, "close").iloc[1])
            is_confirmed = c2_close <= c1_open
        else:
            is_confirmed = c1_red

        if is_confirmed:
            return CatalystComponent("gap_go", "bearish", 30.0, True, {
                "gap_atr": round(gap_atr, 2), "gap_pct": round(raw_gap_pct, 2),
                "confirmed": True, "candles_checked": len(df_5m),
            })

    return CatalystComponent("gap_go", None, 0.0, False, {
        "reason": f"Gap neutral ({gap_atr:.2f} ATR dentro de umbral {min_gap_atr})",
        "gap_atr": round(gap_atr, 2), "gap_pct": round(raw_gap_pct, 2),
    })


def evaluate_c2_sipv_basis(
    df_1h: pd.DataFrame,
    df_5m: pd.DataFrame,
    current_price: float,
    sipv_1h: dict[str, Any],
) -> CatalystComponent:
    """C2: Cruce de BASIS Fibonacci en 1H con confirmacion de cuerpo y sin mecha contraria."""
    if df_1h is None or len(df_1h) < 10 or current_price <= 0:
        return CatalystComponent("sipv_basis_1h", None, 0.0, False, {"reason": "Sin datos 1H"})

    fib = calculate_fibonacci_basis(df_1h, current_price)
    basis = fib["basis"]

    # Evaluar cruce reciente respecto a la vela previa de 1h
    prev_close_1h = float(_safe_series(df_1h, "close").iloc[-2]) if len(df_1h) >= 2 else current_price
    was_below = prev_close_1h < basis
    was_above = prev_close_1h > basis

    is_above = current_price > basis * 1.0005
    is_below = current_price < basis * 0.9995

    # Filtro de mechas SIPV
    upper_rejection = sipv_1h.get("sipv_upper_rejection", False)
    lower_absorption = sipv_1h.get("sipv_lower_absorption", False)

    # Cruce alcista: de abajo hacia arriba del BASIS sin mecha de rechazo superior
    if was_below and is_above:
        if upper_rejection:
            return CatalystComponent("sipv_basis_1h", None, 0.0, False, {
                "reason": "Cruce alcista de BASIS anulado por rechazo SIPV superior (venta institucional)",
                "basis": basis,
            })
        return CatalystComponent("sipv_basis_1h", "bullish", 25.0, True, {
            "type": "BULLISH_BASIS_CROSSOVER", "basis": basis, "price": current_price,
        })

    # Cruce bajista: de arriba hacia abajo del BASIS sin mecha de absorcion inferior
    if was_above and is_below:
        if lower_absorption:
            return CatalystComponent("sipv_basis_1h", None, 0.0, False, {
                "reason": "Cruce bajista de BASIS anulado por absorcion SIPV inferior (compra institucional)",
                "basis": basis,
            })
        return CatalystComponent("sipv_basis_1h", "bearish", 25.0, True, {
            "type": "BEARISH_BASIS_CROSSOVER", "basis": basis, "price": current_price,
        })

    # Continuacion de sesgo si no hubo cruce exacto en la hora actual
    if is_above and not upper_rejection and sipv_1h.get("is_ema3_1h_ascending"):
        return CatalystComponent("sipv_basis_1h", "bullish", 15.0, True, {
            "type": "ABOVE_BASIS_TREND", "basis": basis, "price": current_price,
        })
    elif is_below and not lower_absorption and sipv_1h.get("is_ema3_1h_descending"):
        return CatalystComponent("sipv_basis_1h", "bearish", 15.0, True, {
            "type": "BELOW_BASIS_TREND", "basis": basis, "price": current_price,
        })

    return CatalystComponent("sipv_basis_1h", None, 0.0, False, {
        "reason": "Precio en consolidacion sobre BASIS", "basis": basis,
    })


def evaluate_c3_adx_di(df_5m: pd.DataFrame, cfg: dict[str, Any]) -> CatalystComponent:
    """C3: Inicio de Alto ADX / DI en 5m con suavizado Wilder."""
    adx_res = calculate_adx_wilder(df_5m, period=14)
    adx = adx_res["adx"]
    direction = adx_res["direction"]
    rising = adx_res["adx_rising"]
    di_spread = abs(adx_res["di_spread"])

    min_adx_trigger = float(cfg.get("gate_adx_min") or 20.0)
    adx_override = float(cfg.get("catalyst_adx_override") or 35.0)

    # Disparo de ADX: ADX sobre umbral minimo, creciente y con separacion de DI
    if adx >= min_adx_trigger and rising and di_spread >= 4.0 and direction in ("bullish", "bearish"):
        weight = 35.0 if adx >= adx_override else 25.0
        return CatalystComponent("adx_di_5m", direction, weight, True, {
            "adx": adx, "plus_di": adx_res["plus_di"], "minus_di": adx_res["minus_di"],
            "rising": rising, "is_explosive": bool(adx >= adx_override),
        })

    return CatalystComponent("adx_di_5m", direction, 0.0, False, {
        "reason": f"ADX insuficiente o plano ({adx:.1f}, rising={rising}, spread={di_spread:.1f})",
        "adx": adx,
    })


def evaluate_c4_rebote(symbol: str, df_5m: pd.DataFrame, df_15m: pd.DataFrame) -> CatalystComponent:
    """C4: Modelo REBOTE (15m) evaluado para reversion alcista (Long) o bajista (Short)."""
    try:
        from app.rebote_aduana.rebote_engine import ReboteEngine
        engine = ReboteEngine()
        market_data = {"df_5m": df_5m, "df_15m": df_15m}

        res_long = engine.evaluate(symbol, "long", market_data)
        res_short = engine.evaluate(symbol, "short", market_data)

        if res_long.decision == "ENTER" and res_long.score_final >= 50.0:
            return CatalystComponent("rebote_15m", "bullish", min(35.0, res_long.score_final * 0.4), True, {
                "rule_code": res_long.detail.get("rule_code", "REBOTE_LONG"),
                "score_final": round(res_long.score_final, 1),
            })
        elif res_short.decision == "ENTER" and res_short.score_final >= 50.0:
            return CatalystComponent("rebote_15m", "bearish", min(35.0, res_short.score_final * 0.4), True, {
                "rule_code": res_short.detail.get("rule_code", "REBOTE_SHORT"),
                "score_final": round(res_short.score_final, 1),
            })
    except Exception as e:
        return CatalystComponent("rebote_15m", None, 0.0, False, {"error": str(e)})

    return CatalystComponent("rebote_15m", None, 0.0, False, {"reason": "Sin senal de rebote/climax confirmada"})


def get_sipv_1h_directional_state(
    df_1h: pd.DataFrame,
    current_price: float,
    prev_close: float,
    atr_14: float,
) -> str:
    """Determina el estado direccional de la vela 1H SIPV con buffer simetrico Delta.
    Retorna: 'bullish' | 'bearish' | 'neutral'
    """
    if df_1h is None or len(df_1h) < 1 or current_price <= 0:
        return "neutral"

    delta = calculate_sipv_delta_buffer(current_price, atr_14)
    last_1h = df_1h.iloc[-1]
    o_1h = float(_safe_series(df_1h, "open").iloc[-1])
    c_1h = current_price

    # Si la vela tiene cuerpo claro
    if abs(c_1h - o_1h) >= delta:
        return "bullish" if c_1h > o_1h else "bearish"

    # Si la vela es muy joven o plana, comparar con el cierre previo usando el buffer Delta
    if prev_close > 0:
        if o_1h >= prev_close + delta:
            return "bullish"
        elif o_1h <= prev_close - delta:
            return "bearish"

    return "neutral"


def evaluate_all_catalysts(
    symbol: str,
    current_price: float,
    prev_close: float,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_1h: pd.DataFrame,
    atr_1d: float,
    cfg: dict[str, Any],
) -> ArbitrationResolution:
    """Punto de entrada principal: evalua C1..C4, calcula estado SIPV 1H y resuelve arbitraje."""
    # 1. Metricas SIPV 1H
    from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
    sipv_1h = get_live_1h_candle_and_sipv(symbol, current_price)
    sipv_state = get_sipv_1h_directional_state(df_1h, current_price, prev_close, atr_1d)

    # 2. Evaluar componentes
    c1 = evaluate_c1_gap_and_go(df_5m, prev_close, atr_1d, cfg)
    c2 = evaluate_c2_sipv_basis(df_1h, df_5m, current_price, sipv_1h)
    c3 = evaluate_c3_adx_di(df_5m, cfg)
    c4 = evaluate_c4_rebote(symbol, df_5m, df_15m)

    components = [c1, c2, c3, c4]

    adx_val = c3.detail.get("adx", 0.0)
    adx_dir = c3.direction if c3.triggered else None

    # 3. Arbitraje
    resolution = resolve_arbitration(components, sipv_state, adx_val, adx_dir, cfg)
    return resolution
