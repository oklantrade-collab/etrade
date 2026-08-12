"""
eTrader v4 — QUANTUM SQUEEZE HEDGE & REVERSAL (QSHR / Bb33)
============================================================
Estrategia de Cobertura Dinámica, Ruptura Directa y Reversión Cuántica en Forex y Crypto.

Especificaciones v4:
- Bandas de Fibonacci evaluadas en la temporalidad de 15 MINUTOS (15m Lower_5, Lower_6, Upper_5, Upper_6).
- Protocolo de Escalado Dinámico de Velocidad 1m (1m Velocity Escalation):
  * Al llegar a Lower_5 / Upper_5 en 15m:
    - Si V_1m >= 2.5 (Velocidad Alta viva): MANTENER posición y escalar al objetivo Lower_6 / Upper_6 (15m).
    - Si V_1m < 2.5 (Velocidad Desacelerada): CERRAR y REVERSAR inmediatamente en Lower_5 (15m).
  * Al llegar a Lower_6 / Upper_6 en 15m: CERRAR y REVERSAR incondicionalmente (Objetivo Extremo Final).
- Soporte Dual:
  * Modo Cobertura (Hedge Mode): Protege una posición activa en contra.
  * Modo Ruptura Directa (Standalone Breakout Mode): Opera si hay 0 posiciones activas.
"""

import math
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from app.core.logger import log_info, log_warning, log_error

MODULE = "quantum_squeeze_hedge"

def format_price_precision(symbol: str, price: float) -> float:
    """Formatea la precisión del precio según el activo para evitar rechazos del broker."""
    if not price or pd.isna(price) or math.isnan(price):
        return 0.0
    s = (symbol or '').upper()
    if 'JPY' in s:
        return float(round(price, 3))
    elif s in ('XAUUSD', 'US30', 'US500', 'NAS100', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT'):
        return float(round(price, 2))
    else:
        return float(round(price, 5))

def calculate_15m_fibonacci_levels(df_15m: pd.DataFrame, current_price: float) -> dict:
    """
    Calcula los niveles de Fibonacci Bollinger (Lower_5, Lower_6, Upper_5, Upper_6) en 15 MINUTOS.
    """
    if df_15m is None or len(df_15m) < 20:
        # Fallback de seguridad si no hay suficientes velas de 15m
        return {
            "basis_15m": current_price,
            "lower_5_15m": current_price * 0.98,
            "lower_6_15m": current_price * 0.97,
            "upper_5_15m": current_price * 1.02,
            "upper_6_15m": current_price * 1.03,
            "atr_15m": 0.0
        }

    try:
        last = df_15m.iloc[-1]
        c = df_15m['close']
        basis = float(last.get('basis') or c.rolling(20, min_periods=1).mean().iloc[-1])
        
        # Calcular True Range y ATR 15m
        if 'tr' not in df_15m.columns:
            df_15m['tr'] = np.maximum(
                df_15m['high'] - df_15m['low'],
                np.maximum(abs(df_15m['high'] - df_15m['close'].shift(1)), abs(df_15m['low'] - df_15m['close'].shift(1)))
            )
        atr_15m = float(df_15m['tr'].rolling(14, min_periods=1).mean().iloc[-1])
        if atr_15m <= 0:
            atr_15m = (df_15m['high'].iloc[-1] - df_15m['low'].iloc[-1]) or 0.0010

        # Mapeo de niveles Fibonacci Bollinger en 15m:
        # Level 5 = Basis +/- (5.618 * ATR)
        # Level 6 = Basis +/- (6.618 * ATR)
        lower_5_15m = float(last.get('lower_5') or (basis - (5.618 * atr_15m)))
        lower_6_15m = float(last.get('lower_6') or (basis - (6.618 * atr_15m)))
        upper_5_15m = float(last.get('upper_5') or (basis + (5.618 * atr_15m)))
        upper_6_15m = float(last.get('upper_6') or (basis + (6.618 * atr_15m)))

        return {
            "basis_15m": basis,
            "lower_5_15m": lower_5_15m,
            "lower_6_15m": lower_6_15m,
            "upper_5_15m": upper_5_15m,
            "upper_6_15m": upper_6_15m,
            "atr_15m": atr_15m
        }
    except Exception as e:
        log_error(MODULE, f"Error calculando niveles 15m Fib: {e}")
        return {
            "basis_15m": current_price,
            "lower_5_15m": current_price * 0.98,
            "lower_6_15m": current_price * 0.97,
            "upper_5_15m": current_price * 1.02,
            "upper_6_15m": current_price * 1.03,
            "atr_15m": 0.0
        }

def detect_bollinger_squeeze_expansion(df_5m: pd.DataFrame) -> dict:
    """
    Detecta si las Bandas de Bollinger en 5m están en expansión divergente (Squeeze Expansion).
    """
    if df_5m is None or len(df_5m) < 3:
        return {"is_expanding": False, "upper_slope": 0.0, "lower_slope": 0.0}

    try:
        upper_col = 'upper_1' if 'upper_1' in df_5m.columns else ('upper_bollinger' if 'upper_bollinger' in df_5m.columns else 'basis')
        lower_col = 'lower_1' if 'lower_1' in df_5m.columns else ('lower_bollinger' if 'lower_bollinger' in df_5m.columns else 'basis')

        if upper_col not in df_5m.columns or lower_col not in df_5m.columns:
            basis = df_5m['close'].rolling(20).mean()
            std = df_5m['close'].rolling(20).std()
            upper_series = basis + (2.0 * std)
            lower_series = basis - (2.0 * std)
        else:
            upper_series = df_5m[upper_col]
            lower_series = df_5m[lower_col]

        curr_upper = float(upper_series.iloc[-1])
        prev_upper = float(upper_series.iloc[-2])
        curr_lower = float(lower_series.iloc[-1])
        prev_lower = float(lower_series.iloc[-2])

        curr_bandwidth = curr_upper - curr_lower
        prev_bandwidth = prev_upper - prev_lower

        is_expanding = curr_bandwidth > prev_bandwidth

        return {
            "is_expanding": is_expanding,
            "upper_slope": curr_upper - prev_upper,
            "lower_slope": curr_lower - prev_lower,
            "curr_upper": curr_upper,
            "curr_lower": curr_lower
        }
    except Exception as e:
        log_error(MODULE, f"Error detectando Squeeze Expansion: {e}")
        return {"is_expanding": False, "upper_slope": 0.0, "lower_slope": 0.0}

def check_triple_ema_alignment(df_5m: pd.DataFrame, direction: str) -> bool:
    """Verifica alineación de EMAs en 5m (EMA3, EMA9, EMA20)."""
    if df_5m is None or len(df_5m) < 2:
        return False

    try:
        last = df_5m.iloc[-1]
        ema3 = float(last.get('ma3') or last.get('ema1') or last.get('ema_3') or 0.0)
        ema9 = float(last.get('ma9') or last.get('ema2') or last.get('ema_9') or 0.0)
        ema20 = float(last.get('ma20') or last.get('ema3') or last.get('ema_20') or last.get('basis') or 0.0)

        if ema3 == 0.0 or ema9 == 0.0 or ema20 == 0.0:
            c = df_5m['close']
            ema3 = float(c.ewm(span=3, adjust=False).mean().iloc[-1])
            ema9 = float(c.ewm(span=9, adjust=False).mean().iloc[-1])
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])

        if direction.lower() in ('bearish', 'short', 'long_exit'):
            return (ema3 < ema9) and (ema9 < ema20)
        elif direction.lower() in ('bullish', 'long', 'short_exit'):
            return (ema3 > ema9) and (ema9 > ema20)

        return False
    except Exception as e:
        log_error(MODULE, f"Error verificando alineación Triple EMA: {e}")
        return False

def calculate_1m_velocity(df_1m: pd.DataFrame) -> dict:
    """Calcula la velocidad del mercado en 1 minuto."""
    if df_1m is None or len(df_1m) < 14:
        return {"v_1m_score": 0.0, "is_high_velocity": False, "direction": "NEUTRAL"}

    try:
        last = df_1m.iloc[-1]
        c = float(last['close'])
        o = float(last['open'])
        body_size = abs(c - o)

        if 'tr' not in df_1m.columns:
            df_1m['tr'] = np.maximum(
                df_1m['high'] - df_1m['low'],
                np.maximum(abs(df_1m['high'] - df_1m['close'].shift(1)), abs(df_1m['low'] - df_1m['close'].shift(1)))
            )
        atr_1m = float(df_1m['tr'].rolling(14, min_periods=1).mean().iloc[-1])
        if atr_1m <= 0:
            atr_1m = body_size if body_size > 0 else 0.0001

        price_velocity = body_size / atr_1m
        vol_curr = float(last['volume'])
        vol_sma14 = float(df_1m['volume'].rolling(14, min_periods=1).mean().iloc[-1])
        volume_ratio = vol_curr / vol_sma14 if vol_sma14 > 0 else 1.0

        v_1m = price_velocity * volume_ratio
        is_high_velocity = v_1m >= 2.5
        direction = "BEARISH_SURGE" if c < o else "BULLISH_SURGE"

        return {
            "v_1m_score": round(v_1m, 2),
            "is_high_velocity": is_high_velocity,
            "direction": direction,
            "price_velocity": round(price_velocity, 2),
            "volume_ratio": round(volume_ratio, 2)
        }
    except Exception as e:
        log_error(MODULE, f"Error calculando velocidad 1m: {e}")
        return {"v_1m_score": 0.0, "is_high_velocity": False, "direction": "NEUTRAL"}

def calculate_hedge_sl(breakout_candle: pd.Series, hedge_side: str, symbol: str, buffer_pips: float = 2.0) -> float:
    """Calcula el Stop Loss estricto para la posición de Cobertura o Entrada Directa."""
    is_jpy = 'JPY' in (symbol or '').upper()
    pip_factor = 0.01 if is_jpy else 0.0001
    
    if hedge_side.lower() in ('short', 'sell'):
        high_price = float(breakout_candle['high'])
        sl_price = high_price + (buffer_pips * pip_factor)
    else:
        low_price = float(breakout_candle['low'])
        sl_price = low_price - (buffer_pips * pip_factor)

    return format_price_precision(symbol, sl_price)

def evaluate_qshr_hedge_signal(
    symbol: str,
    df_5m: pd.DataFrame,
    df_1m: pd.DataFrame,
    df_15m: pd.DataFrame = None,
    active_position: dict = None,
    market_type: str = 'forex_futures'
) -> dict | None:
    """
    Evaluador Principal QUANTUM SQUEEZE HEDGE & REVERSAL (Bb33_QSHR).
    Soporta Cobertura (con posición activa) y Entrada Directa (0 posiciones activas).
    Usa niveles de 15 MINUTOS (Lower_5_15m, Lower_6_15m) con escalado por velocidad de 1m.
    """
    if df_5m is None or df_5m.empty:
        return None

    try:
        last_5m = df_5m.iloc[-1]
        current_price = float(last_5m['close'])
        
        # 1. Obtener niveles de 15 Minutos (Lower_5, Lower_6, Upper_5, Upper_6)
        levels_15m = calculate_15m_fibonacci_levels(df_15m, current_price)
        lower_5_15m = levels_15m['lower_5_15m']
        lower_6_15m = levels_15m['lower_6_15m']
        upper_5_15m = levels_15m['upper_5_15m']
        upper_6_15m = levels_15m['upper_6_15m']

        # 2. Detectar Expansión Squeeze 5m
        squeeze = detect_bollinger_squeeze_expansion(df_5m)
        is_expanding = squeeze['is_expanding']
        vel_info = calculate_1m_velocity(df_1m)

        # =====================================================================
        # MODO 1: RUPTURA DIRECTA (0 POSICIONES ACTIVAS EN EL PAR)
        # =====================================================================
        if not active_position:
            # 1.1 Ruptura Bajista Directa (0 posiciones)
            is_bearish_breakout = (last_5m['close'] < last_5m['open']) and (current_price <= squeeze['curr_lower'])
            ema_bearish = check_triple_ema_alignment(df_5m, 'bearish')
            vel_bearish = vel_info['is_high_velocity'] and (vel_info['direction'] == 'BEARISH_SURGE')

            if is_expanding and is_bearish_breakout and ema_bearish and vel_bearish:
                sl_price = calculate_hedge_sl(last_5m, 'short', symbol)
                return {
                    "action": "open_direct_short",
                    "rule_code": "Bb33_QSHR_DIRECT_SHORT",
                    "lots": 0.01, # Lotaje inicial o dinámico por gestión de riesgo
                    "sl_price": sl_price,
                    "reason": f"QSHR Direct: Ruptura Bajista 5m confirmada (V_1m={vel_info['v_1m_score']})"
                }

            # 1.2 Ruptura Alcista Directa (0 posiciones)
            is_bullish_breakout = (last_5m['close'] > last_5m['open']) and (current_price >= squeeze['curr_upper'])
            ema_bullish = check_triple_ema_alignment(df_5m, 'bullish')
            vel_bullish = vel_info['is_high_velocity'] and (vel_info['direction'] == 'BULLISH_SURGE')

            if is_expanding and is_bullish_breakout and ema_bullish and vel_bullish:
                sl_price = calculate_hedge_sl(last_5m, 'long', symbol)
                return {
                    "action": "open_direct_long",
                    "rule_code": "Bb33_QSHR_DIRECT_LONG",
                    "lots": 0.01,
                    "sl_price": sl_price,
                    "reason": f"QSHR Direct: Ruptura Alcista 5m confirmada (V_1m={vel_info['v_1m_score']})"
                }

            return None

        # =====================================================================
        # MODO 2: COBERTURA Y GESTIÓN (CON POSICIÓN ACTIVA)
        # =====================================================================
        orig_side = (active_position.get('side') or '').lower()
        orig_lots = abs(float(active_position.get('lots') or active_position.get('size') or 0))

        # -------------------------------------------------------------
        # CASO A: Posición Original es LONG (Breakout Bajista)
        # -------------------------------------------------------------
        if orig_side in ('long', 'buy'):
            has_hedge_short = active_position.get('has_hedge') or (active_position.get('rule_code') == 'Bb33_QSHR_HEDGE')
            is_bearish_breakout = (last_5m['close'] < last_5m['open']) and (current_price <= squeeze['curr_lower'])

            # A1. Abrir Cobertura SHORT si no existe
            if is_expanding and is_bearish_breakout and not has_hedge_short:
                hedge_sl = calculate_hedge_sl(last_5m, 'short', symbol)
                return {
                    "action": "open_hedge_short",
                    "rule_code": "Bb33_QSHR_HEDGE",
                    "lots": orig_lots,
                    "sl_price": hedge_sl,
                    "reason": "QSHR: Cobertura SHORT 1:1 por Squeeze Expansion bajista"
                }

            # A2. Cierre de LONG Antigua por Filtro de 4 Factores
            ema_aligned_bearish = check_triple_ema_alignment(df_5m, 'bearish')
            at_lower_band = (current_price <= squeeze['curr_lower'])
            high_vel_bearish = vel_info['is_high_velocity'] and (vel_info['direction'] == 'BEARISH_SURGE')

            if ema_aligned_bearish and is_expanding and at_lower_band and high_vel_bearish:
                return {
                    "action": "close_original_long",
                    "rule_code": "Bb33_QSHR_EXIT",
                    "reason": f"QSHR Exit: 4 Factores validados (EMA3<9<20, Squeeze Exp, Lower Band 5m, V_1m={vel_info['v_1m_score']})"
                }

            # A3. EVALUACIÓN DINÁMICA DE OBJETIVO DE 15 MINUTOS (Lower_5_15m vs Lower_6_15m)
            if current_price <= lower_5_15m:
                # Llegamos al Lower_5 de 15 MINUTOS -> Revisar velocidad 1m
                if current_price <= lower_6_15m:
                    # Llegada al Lower_6 de 15m (Objetivo Extremo Final) -> Cerrar SHORT + Reversión LONG
                    return {
                        "action": "reversal_at_level6",
                        "reversal_side": "long",
                        "rule_code": "Bb33_QSHR_REVERSAL_L6_15M",
                        "reason": f"QSHR Reversal 15m: Alcanzado Lower_6 15m ({lower_6_15m:.5f}). Cerrar SHORT e iniciar Reversal LONG."
                    }
                else:
                    # Estamos entre Lower_5 15m y Lower_6 15m
                    if vel_info['is_high_velocity'] and (vel_info['direction'] == 'BEARISH_SURGE'):
                        # Velocidad 1m sigue alta -> MANTENER Y ESCALAR AL LOWER_6 DE 15M
                        log_info(MODULE, f"🚀 [QSHR 15M ESCALATION] {symbol}: En Lower_5 15m ({lower_5_15m:.5f}), velocidad 1m ALTA (V={vel_info['v_1m_score']}). Escalando a Lower_6 15m!")
                    else:
                        # Velocidad desaceleró -> CERRAR Y REVERSAR EN LOWER_5 15M
                        return {
                            "action": "reversal_at_level5",
                            "reversal_side": "long",
                            "rule_code": "Bb33_QSHR_REVERSAL_L5_15M",
                            "reason": f"QSHR Reversal 15m: Alcanzado Lower_5 15m ({lower_5_15m:.5f}) con velocidad desacelerada (V={vel_info['v_1m_score']}). Cerrar e iniciar Reversal LONG."
                        }

        # -------------------------------------------------------------
        # CASO B: Posición Original es SHORT (Breakout Alcista)
        # -------------------------------------------------------------
        elif orig_side in ('short', 'sell'):
            has_hedge_long = active_position.get('has_hedge') or (active_position.get('rule_code') == 'Bb33_QSHR_HEDGE')
            is_bullish_breakout = (last_5m['close'] > last_5m['open']) and (current_price >= squeeze['curr_upper'])

            # B1. Abrir Cobertura LONG si no existe
            if is_expanding and is_bullish_breakout and not has_hedge_long:
                hedge_sl = calculate_hedge_sl(last_5m, 'long', symbol)
                return {
                    "action": "open_hedge_long",
                    "rule_code": "Bb33_QSHR_HEDGE",
                    "lots": orig_lots,
                    "sl_price": hedge_sl,
                    "reason": "QSHR: Cobertura LONG 1:1 por Squeeze Expansion alcista"
                }

            # B2. Cierre de SHORT Antigua por Filtro de 4 Factores
            ema_aligned_bullish = check_triple_ema_alignment(df_5m, 'bullish')
            at_upper_band = (current_price >= squeeze['curr_upper'])
            high_vel_bullish = vel_info['is_high_velocity'] and (vel_info['direction'] == 'BULLISH_SURGE')

            if ema_aligned_bullish and is_expanding and at_upper_band and high_vel_bullish:
                return {
                    "action": "close_original_short",
                    "rule_code": "Bb33_QSHR_EXIT",
                    "reason": f"QSHR Exit: 4 Factores validados (EMA3>9>20, Squeeze Exp, Upper Band 5m, V_1m={vel_info['v_1m_score']})"
                }

            # B3. EVALUACIÓN DINÁMICA DE OBJETIVO DE 15 MINUTOS (Upper_5_15m vs Upper_6_15m)
            if current_price >= upper_5_15m:
                if current_price >= upper_6_15m:
                    return {
                        "action": "reversal_at_level6",
                        "reversal_side": "short",
                        "rule_code": "Bb33_QSHR_REVERSAL_L6_15M",
                        "reason": f"QSHR Reversal 15m: Alcanzado Upper_6 15m ({upper_6_15m:.5f}). Cerrar LONG e iniciar Reversal SHORT."
                    }
                else:
                    if vel_info['is_high_velocity'] and (vel_info['direction'] == 'BULLISH_SURGE'):
                        log_info(MODULE, f"🚀 [QSHR 15M ESCALATION] {symbol}: En Upper_5 15m ({upper_5_15m:.5f}), velocidad 1m ALTA (V={vel_info['v_1m_score']}). Escalando a Upper_6 15m!")
                    else:
                        return {
                            "action": "reversal_at_level5",
                            "reversal_side": "short",
                            "rule_code": "Bb33_QSHR_REVERSAL_L5_15M",
                            "reason": f"QSHR Reversal 15m: Alcanzado Upper_5 15m ({upper_5_15m:.5f}) con velocidad desacelerada (V={vel_info['v_1m_score']}). Cerrar e iniciar Reversal SHORT."
                        }

        return None
    except Exception as e:
        log_error(MODULE, f"Error evaluando estrategia QSHR v4: {e}")
        return None
