"""
eTrader v5.0 — VOLATILITY MOMENTUM EXPANSION (VME) Exit & Defense Engine
Motor de supervisión, Stop Loss Dinámico y Trailing Stop Híbrido en 15 minutos
para posiciones abiertas bajo estrategia VME (STOCKS y OPCIONES CALLs/PUTs).

5 Gatillos de Cierre en Cascada:
1. Quiebre de Ribbon 15m: EMA3 < EMA9 (LONG) / EMA3 > EMA9 (PUT).
2. Clímax Parabólico 1H: RSI >= 80 (LONG) / RSI <= 20 (PUT).
3. Bandas Fibonacci Extremas: UPPER_5 (50% TP1) / UPPER_6 (100% TP2) en 15m/1H.
4. Inflexión de Pendiente EMA3 1H: se vuelve plana o descendente (LONG) / plana o ascendente (PUT).
5. SIPV Reversión 1H: señal de giro o SELL (LONG) / giro o BUY (PUT).

Stop Loss Dinámico 15m:
- Ratchet de EMA9: si EMA9_t > EMA9_{t-1}, SL = EMA9 - delta (LONG).
- Delta adaptativo: max(0.05, 0.35 * ATR_15m).
- Monotonicidad estricta (solo sube en LONG, solo baja en PUT).

Trailing Stop Híbrido 15m (Nueva Propuesta):
- Si High > BB_Upper y Close > Open en 15m:
  Mid = Open + (Close - Open) / 2
  Si (Close - Open) >= 0.5 * ATR: TSL = Mid
  Else: TSL = Close - 1.2 * ATR
  Piso mínimo con VWAP: TSL >= VWAP + 0.05
  Monotónico estricto.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from app.core.logger import log_info, log_debug, log_warning
from app.stocks.vme_expansion_engine import _ensure_indicators_15m, _ensure_indicators_1h

MODULE = "vme_defense"


def evaluate_vme_exit(
    position: Dict[str, Any],
    df_15m: Optional[pd.DataFrame],
    df_1h: Optional[pd.DataFrame],
    current_price: Optional[float] = None,
    current_option_premium: Optional[float] = None,
    sipv_signal_1h: Optional[str] = None,
    position_age_minutes: float = 0.0
) -> Dict[str, Any]:
    """
    Evalúa la salida, Stop Loss y Trailing Stop para posiciones abiertas VME.
    Retorna un diccionario con la decisión de salida y niveles dinámicos actualizados.
    """
    res = {
        "should_exit": False,
        "exit_type": "NONE",       # "FULL", "PARTIAL", "NONE"
        "partial_ratio": 0.0,      # 0.50 para UPPER_5
        "rule_code": "",
        "reason": "",
        "new_stop_loss": 0.0,
        "new_trailing_sl": 0.0,
        "metrics": {}
    }

    if df_15m is None or len(df_15m) < 5 or df_1h is None or len(df_1h) < 5:
        res["reason"] = "Datos insuficientes para evaluación de salida"
        return res

    df_15m_calc = _ensure_indicators_15m(df_15m)
    df_1h_calc = _ensure_indicators_1h(df_1h)

    last_15m = df_15m_calc.iloc[-1]
    prev_15m = df_15m_calc.iloc[-2]
    last_1h = df_1h_calc.iloc[-1]
    prev_1h = df_1h_calc.iloc[-2]

    price = float(current_price or last_15m["close"])
    if price <= 0:
        return res

    # Determinar dirección (Bullish o Bearish)
    dir_str = str(position.get("direction") or position.get("strategy_type") or "").lower()
    is_bullish = ("call" in dir_str or "bull" in dir_str or "long" in dir_str or dir_str == "buy")

    entry_p = float(position.get("avg_price") or position.get("entry_price") or position.get("entry_debit") or price)
    current_sl = float(position.get("stop_loss") or position.get("exit_plan", {}).get("stop_loss_underlying") or 0.0)
    current_tsl = float(position.get("trailing_sl_price") or position.get("exit_plan", {}).get("trailing_sl_underlying") or 0.0)

    # Métricas 15m
    ema3_15m = float(last_15m.get("ema_3") or price)
    ema9_15m = float(last_15m.get("ema_9") or price)
    ema9_15m_prev = float(prev_15m.get("ema_9") or price)
    atr_15m = float(last_15m.get("atr_14") or (price * 0.015))
    vwap_15m = float(last_15m.get("vwap") or price)
    bb_upper_15m = float(last_15m.get("bb_upper") or (price * 1.03))
    bb_lower_15m = float(last_15m.get("bb_lower") or (price * 0.97))
    high_15m = float(last_15m["high"])
    low_15m = float(last_15m["low"])
    open_15m = float(last_15m["open"])
    close_15m = float(last_15m["close"])

    # Bandas Fibonacci Extremas (Upper 5 = +2.618σ, Upper 6 = +3.618σ aproximadas por BB std)
    bb_std_15m = (bb_upper_15m - float(last_15m.get("ema_20") or price)) / 2.0
    upper_5 = float(last_15m.get("upper_5") or (price + bb_std_15m * 2.618))
    upper_6 = float(last_15m.get("upper_6") or (price + bb_std_15m * 3.618))
    lower_5 = float(last_15m.get("lower_5") or (price - bb_std_15m * 2.618))
    lower_6 = float(last_15m.get("lower_6") or (price - bb_std_15m * 3.618))

    # Métricas 1H
    rsi_1h = float(last_1h.get("rsi_14") or 50.0)
    ema3_1h = float(last_1h.get("ema_3") or price)
    ema3_1h_prev = float(prev_1h.get("ema_3") or price)
    slope_ema3_1h = (ema3_1h - ema3_1h_prev) / ema3_1h_prev if ema3_1h_prev > 0 else 0.0

    delta = max(0.05, round(0.35 * atr_15m, 2))

    res["metrics"] = {
        "price": price,
        "entry_price": entry_p,
        "ema3_15m": round(ema3_15m, 2),
        "ema9_15m": round(ema9_15m, 2),
        "ema9_15m_prev": round(ema9_15m_prev, 2),
        "atr_15m": round(atr_15m, 2),
        "delta": delta,
        "vwap": round(vwap_15m, 2),
        "rsi_1h": round(rsi_1h, 1),
        "slope_ema3_1h": round(slope_ema3_1h, 5),
        "upper_5": round(upper_5, 2),
        "upper_6": round(upper_6, 2),
        "lower_5": round(lower_5, 2),
        "lower_6": round(lower_6, 2),
    }

    # ════════════════════════════════════════════════════════
    # A. DEFENSA OPCIONES: REGLAS SOBRE PRIMA DEL CONTRATO
    # ════════════════════════════════════════════════════════
    if current_option_premium is not None and current_option_premium > 0:
        entry_debit = float(position.get("entry_debit") or entry_p)
        highest_p = float(position.get("highest_premium_seen") or position.get("exit_plan", {}).get("highest_premium_seen") or entry_debit)
        highest_p = max(highest_p, current_option_premium)

        # 1. Hard Stop Loss en Prima (-35%)
        if current_option_premium <= entry_debit * 0.65:
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_OPT_HARD_SL",
                "reason": f"Hard Stop Loss Opciones activado: Prima ${current_option_premium:.2f} <= ${entry_debit*0.65:.2f} (-35%)"
            }

        # 2. Breakeven Shield (+15% pico o subyacente +1.0% -> piso +1%)
        und_gain_pct = ((price - entry_p) / entry_p * 100.0) if (is_bullish and entry_p > 0) else ((entry_p - price) / entry_p * 100.0) if entry_p > 0 else 0.0
        if (highest_p >= entry_debit * 1.15 or und_gain_pct >= 1.0) and current_option_premium <= entry_debit * 1.01:
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_OPT_BREAKEVEN",
                "reason": f"Breakeven Shield activado: Ganancia pico (+{(highest_p/entry_debit - 1)*100:.1f}%) o subyacente (+{und_gain_pct:.2f}%) protegida en costo ${entry_debit*1.01:.2f}"
            }

        # 3. Trailing Ratchet Tier 2 (+30% pico -> asegura +15%)
        if highest_p >= entry_debit * 1.30 and current_option_premium <= entry_debit * 1.15:
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_OPT_RATCHET_TIER2",
                "reason": f"Trailing Ratchet Tier 2 activado: Pico (+{(highest_p/entry_debit - 1)*100:.1f}%) protegiendo piso de +15% (${entry_debit*1.15:.2f})"
            }

        # 4. Stall Guard (25 minutos aletargada sin impulso)
        if position_age_minutes >= 25.0 and current_option_premium < entry_debit * 1.03:
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_OPT_STALL_GUARD",
                "reason": f"Stall Guard activado: Posición estancada {position_age_minutes:.0f}m sin impulso comprador. Salida defensiva."
            }

    # ════════════════════════════════════════════════════════
    # B. STOP LOSS DINÁMICO 15M (EMA9 RATCHET & BREAKEVEN SHIELD A +1.0%)
    # ════════════════════════════════════════════════════════
    new_sl = current_sl
    if is_bullish:
        if ema9_15m > ema9_15m_prev:
            prop_sl = round(ema9_15m - delta, 2)
            new_sl = max(current_sl, prop_sl)
        # Breakeven Lock para STOCKS a +1.0% de ganancia
        und_gain_pct = ((price - entry_p) / entry_p * 100.0) if entry_p > 0 else 0.0
        if und_gain_pct >= 1.0:
            prop_be = round(entry_p + 0.02, 2)
            if prop_be > new_sl and prop_be < price:
                new_sl = prop_be
    else:
        if ema9_15m < ema9_15m_prev:
            prop_sl = round(ema9_15m + delta, 2)
            new_sl = min(current_sl, prop_sl) if current_sl > 0 else prop_sl
        und_gain_pct = ((entry_p - price) / entry_p * 100.0) if entry_p > 0 else 0.0
        if und_gain_pct >= 1.0:
            prop_be = round(entry_p - 0.02, 2)
            if (prop_be < new_sl or new_sl <= 0) and prop_be > price:
                new_sl = prop_be

    res["new_stop_loss"] = new_sl

    # ════════════════════════════════════════════════════════
    # C. TRAILING STOP HÍBRIDO 15M (50% CUERPO + ATR + VWAP)
    # ════════════════════════════════════════════════════════
    new_tsl = current_tsl
    if is_bullish:
        # Condición: Vela verde impulsiva de 15m penetra/supera Banda Superior
        if high_15m > bb_upper_15m and close_15m > open_15m:
            body_range = close_15m - open_15m
            mid_body = open_15m + (body_range / 2.0)

            # Si el cuerpo es potente (>= 0.5 * ATR), usar el 50% de la vela
            if body_range >= (0.5 * atr_15m):
                cand_tsl = mid_body
            else:
                # Si es cuerpo estrecho, dar holgura con 1.2 * ATR
                cand_tsl = close_15m - (1.2 * atr_15m)

            # Piso de protección institucional con VWAP si ya está en ganancia
            if price > entry_p and vwap_15m > 0:
                cand_tsl = max(cand_tsl, round(vwap_15m + 0.05, 2))

            new_tsl = max(current_tsl, round(cand_tsl, 2))
    else:
        # Inversa para PUT: Vela roja impulsiva penetra Banda Inferior
        if low_15m < bb_lower_15m and close_15m < open_15m:
            body_range = open_15m - close_15m
            mid_body = open_15m - (body_range / 2.0)

            if body_range >= (0.5 * atr_15m):
                cand_tsl = mid_body
            else:
                cand_tsl = close_15m + (1.2 * atr_15m)

            if price < entry_p and vwap_15m > 0:
                cand_tsl = min(cand_tsl, round(vwap_15m - 0.05, 2))

            new_tsl = min(current_tsl, round(cand_tsl, 2)) if current_tsl > 0 else round(cand_tsl, 2)

    res["new_trailing_sl"] = new_tsl

    # ════════════════════════════════════════════════════════
    # D. CHEQUEO DE EJECUCIÓN POR SL O TRAILING STOP ALCANZADO
    # ════════════════════════════════════════════════════════
    if is_bullish:
        if new_sl > 0 and price <= new_sl:
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_SL_HIT",
                "reason": f"Stop Loss Dinámico alcanzado: Precio (${price:.2f}) <= SL (${new_sl:.2f})"
            }
        if new_tsl > 0 and price <= new_tsl:
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_TSL_HIT",
                "reason": f"Trailing Stop Híbrido 15m alcanzado: Precio (${price:.2f}) <= TSL (${new_tsl:.2f})"
            }
    else:
        if new_sl > 0 and price >= new_sl:
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_SL_HIT",
                "reason": f"Stop Loss Dinámico PUT alcanzado: Precio (${price:.2f}) >= SL (${new_sl:.2f})"
            }
        if new_tsl > 0 and price >= new_tsl:
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_TSL_HIT",
                "reason": f"Trailing Stop Híbrido 15m PUT alcanzado: Precio (${price:.2f}) >= TSL (${new_tsl:.2f})"
            }

    # ════════════════════════════════════════════════════════
    # E. LOS 5 GATILLOS LÓGICOS DE CIERRE EN CASCADA
    # ════════════════════════════════════════════════════════

    # Gatillo 1: Quiebre de Ribbon 15m (EMA3 < EMA9 en LONG / EMA3 > EMA9 en PUT)
    if is_bullish and (ema3_15m < ema9_15m or price < (ema9_15m - 0.05)):
        return {
            **res,
            "should_exit": True,
            "exit_type": "FULL",
            "rule_code": "VME_EXIT_RIBBON_15M",
            "reason": f"Quiebre de Ribbon 15m: EMA3 (${ema3_15m:.2f}) < EMA9 (${ema9_15m:.2f}). Fin de fase impulsiva."
        }
    elif not is_bullish and (ema3_15m > ema9_15m or price > (ema9_15m + 0.05)):
        return {
            **res,
            "should_exit": True,
            "exit_type": "FULL",
            "rule_code": "VME_EXIT_RIBBON_15M",
            "reason": f"Quiebre de Ribbon 15m PUT: EMA3 (${ema3_15m:.2f}) > EMA9 (${ema9_15m:.2f}). Fin de fase bajista."
        }

    # Gatillo 2: Clímax 1H (RSI 1H >= 80 en LONG / <= 20 en PUT)
    if is_bullish and rsi_1h >= 80.0:
        return {
            **res,
            "should_exit": True,
            "exit_type": "FULL",
            "rule_code": "VME_EXIT_RSI_CLIMAX_1H",
            "reason": f"Clímax Parabólico 1H: RSI1H={rsi_1h:.1f} >= 80.0. Toma de ganancias total en euforia extrema."
        }
    elif not is_bullish and rsi_1h <= 20.0:
        return {
            **res,
            "should_exit": True,
            "exit_type": "FULL",
            "rule_code": "VME_EXIT_RSI_CLIMAX_1H",
            "reason": f"Clímax de Pánico 1H PUT: RSI1H={rsi_1h:.1f} <= 20.0. Toma de ganancias total en capitulación."
        }

    # Gatillo 3: Bandas Fibonacci Extremas (UPPER_6 / LOWER_6 Total o UPPER_5 / LOWER_5 Parcial)
    if is_bullish:
        if price >= upper_6:
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_UPPER6_TOTAL",
                "reason": f"Extensión Fibonacci Extrema: Precio (${price:.2f}) >= UPPER_6 (${upper_6:.2f}). Cierre 100%."
            }
        elif price >= upper_5:
            # TP1: Cierre del 50%
            return {
                **res,
                "should_exit": True,
                "exit_type": "PARTIAL",
                "partial_ratio": 0.50,
                "rule_code": "VME_EXIT_UPPER5_TP1",
                "reason": f"Fibonacci Target 1: Precio (${price:.2f}) >= UPPER_5 (${upper_5:.2f}). Cierre Parcial 50%."
            }
    else:
        if price <= lower_6:
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_LOWER6_TOTAL",
                "reason": f"Extensión Fibonacci Extrema PUT: Precio (${price:.2f}) <= LOWER_6 (${lower_6:.2f}). Cierre 100%."
            }
        elif price <= lower_5:
            return {
                **res,
                "should_exit": True,
                "exit_type": "PARTIAL",
                "partial_ratio": 0.50,
                "rule_code": "VME_EXIT_LOWER5_TP1",
                "reason": f"Fibonacci Target 1 PUT: Precio (${price:.2f}) <= LOWER_5 (${lower_5:.2f}). Cierre Parcial 50%."
            }

    # Gatillo 4: Inflexión de Pendiente EMA3 1H (Plana o descendente en LONG / plana o ascendente en PUT)
    if is_bullish and slope_ema3_1h <= 0.0 and (price > entry_p * 1.01):
        return {
            **res,
            "should_exit": True,
            "exit_type": "FULL",
            "rule_code": "VME_EXIT_EMA3_SLOPE_1H",
            "reason": f"Inflexión de Impulso 1H: Pendiente EMA3 1H ({slope_ema3_1h:+.5f}) se vuelve plana/negativa. Asegurando PnL."
        }
    elif not is_bullish and slope_ema3_1h >= 0.0 and (price < entry_p * 0.99):
        return {
            **res,
            "should_exit": True,
            "exit_type": "FULL",
            "rule_code": "VME_EXIT_EMA3_SLOPE_1H",
            "reason": f"Inflexión de Impulso 1H PUT: Pendiente EMA3 1H ({slope_ema3_1h:+.5f}) se vuelve plana/positiva. Asegurando PnL."
        }

    # Gatillo 5: SIPV Reversión 1H
    if sipv_signal_1h:
        sig_upper = sipv_signal_1h.upper()
        if is_bullish and ("SELL" in sig_upper or "BEARISH" in sig_upper):
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_SIPV_1H",
                "reason": f"Alerta de Reversión SIPV 1H: {sipv_signal_1h}. Giro de velas detectado."
            }
        elif not is_bullish and ("BUY" in sig_upper or "BULLISH" in sig_upper):
            return {
                **res,
                "should_exit": True,
                "exit_type": "FULL",
                "rule_code": "VME_EXIT_SIPV_1H",
                "reason": f"Alerta de Reversión SIPV 1H PUT: {sipv_signal_1h}. Giro alcista de velas detectado."
            }

    return res
