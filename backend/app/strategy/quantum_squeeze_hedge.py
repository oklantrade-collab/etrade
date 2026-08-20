"""
eTrader v5 — QUANTUM SQUEEZE HEDGE & REVERSAL (QSHR / Bb33)
============================================================
Estrategia de Cobertura Dinámica, Ruptura Directa y Reversión Cuántica en Forex y Crypto.

Especificaciones v5:
- Scanner Multi-Par Autónomo: Detecta Squeeze Breakouts en cualquier par (LONG y SHORT).
- Velocidad 5m Nativa (calculate_5m_velocity): Sustituye la dependencia de velas de 1m.
- Sistema de Presión y Volumen (SIPV) en 15 MINUTOS: Detecta clímax y agotamiento de volumen real.
- Salida Dual "Ride & Close":
  * Estrategia Pasiva: Trailing Stop dinámico anclado a EMA9 en 5m.
  * Estrategia Activa: Cierre MARKET inmediato en 15m ante sobre-extensión de bandas + Clímax SIPV.
- Bandas de Fibonacci en 15 MINUTOS (Upper_5, Upper_6, Lower_5, Lower_6) para Reversión Cuántica.
- Soporte Dual: Cobertura (Hedge Mode 1:1) y Ruptura Directa a Mercado (MARKET Order).
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
    Calcula los niveles de Fibonacci Bollinger (Lower_5, Lower_6, Upper_5, Upper_6, Upper/Lower Bands) en 15 MINUTOS.
    """
    if df_15m is None or len(df_15m) < 20:
        return {
            "basis_15m": current_price,
            "upper_band_15m": current_price * 1.01,
            "lower_band_15m": current_price * 0.99,
            "lower_5_15m": current_price * 0.98,
            "lower_6_15m": current_price * 0.97,
            "upper_5_15m": current_price * 1.02,
            "upper_6_15m": current_price * 1.03,
            "atr_15m": 0.0010
        }

    try:
        last = df_15m.iloc[-1]
        c = df_15m['close']
        basis = float(last.get('basis') or c.rolling(20, min_periods=1).mean().iloc[-1])
        std = float(c.rolling(20, min_periods=1).std().iloc[-1])
        if std == 0:
            std = current_price * 0.002
            
        upper_band = float(last.get('upper_1') or last.get('upper_bollinger') or (basis + 2.0 * std))
        lower_band = float(last.get('lower_1') or last.get('lower_bollinger') or (basis - 2.0 * std))

        if 'tr' not in df_15m.columns:
            df_15m['tr'] = np.maximum(
                df_15m['high'] - df_15m['low'],
                np.maximum(abs(df_15m['high'] - df_15m['close'].shift(1)), abs(df_15m['low'] - df_15m['close'].shift(1)))
            )
        atr_15m = float(df_15m['tr'].rolling(14, min_periods=1).mean().iloc[-1])
        if atr_15m <= 0:
            atr_15m = (df_15m['high'].iloc[-1] - df_15m['low'].iloc[-1]) or 0.0010

        # Nivel 5 = Basis +/- (5.618 * ATR)
        # Nivel 6 = Basis +/- (6.618 * ATR)
        lower_5_15m = float(last.get('lower_5') or (basis - (5.618 * atr_15m)))
        lower_6_15m = float(last.get('lower_6') or (basis - (6.618 * atr_15m)))
        upper_5_15m = float(last.get('upper_5') or (basis + (5.618 * atr_15m)))
        upper_6_15m = float(last.get('upper_6') or (basis + (6.618 * atr_15m)))

        return {
            "basis_15m": basis,
            "upper_band_15m": upper_band,
            "lower_band_15m": lower_band,
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
            "upper_band_15m": current_price * 1.01,
            "lower_band_15m": current_price * 0.99,
            "lower_5_15m": current_price * 0.98,
            "lower_6_15m": current_price * 0.97,
            "upper_5_15m": current_price * 1.02,
            "upper_6_15m": current_price * 1.03,
            "atr_15m": 0.0010
        }

def detect_bollinger_squeeze_expansion(df_5m: pd.DataFrame) -> dict:
    """
    Detecta si las Bandas de Bollinger en 5m presentan compresión previa y expansión divergente activa.
    """
    if df_5m is None or len(df_5m) < 20:
        return {
            "is_expanding": False,
            "is_divergent": False,
            "was_compressed": False,
            "is_squeeze_breakout": False,
            "bandwidth_ratio": 1.0,
            "upper_slope": 0.0,
            "lower_slope": 0.0,
            "curr_upper": 0.0,
            "curr_lower": 0.0
        }

    try:
        upper_col = 'upper_1' if 'upper_1' in df_5m.columns else ('upper_bollinger' if 'upper_bollinger' in df_5m.columns else None)
        lower_col = 'lower_1' if 'lower_1' in df_5m.columns else ('lower_bollinger' if 'lower_bollinger' in df_5m.columns else None)

        if not upper_col or not lower_col:
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

        bandwidth_series = upper_series - lower_series
        curr_bandwidth = float(bandwidth_series.iloc[-1])
        prev_bandwidth = float(bandwidth_series.iloc[-2])
        avg_bandwidth_20 = float(bandwidth_series.iloc[-20:].mean()) if len(bandwidth_series) >= 20 else curr_bandwidth

        upper_slope = curr_upper - prev_upper
        lower_slope = curr_lower - prev_lower

        is_expanding = curr_bandwidth > prev_bandwidth
        is_divergent = (upper_slope > 0) and (lower_slope < 0)
        was_compressed = prev_bandwidth < (avg_bandwidth_20 * 0.90) if avg_bandwidth_20 > 0 else False
        is_squeeze_breakout = is_expanding and (is_divergent or was_compressed)

        bandwidth_ratio = curr_bandwidth / avg_bandwidth_20 if avg_bandwidth_20 > 0 else 1.0

        return {
            "is_expanding": is_expanding,
            "is_divergent": is_divergent,
            "was_compressed": was_compressed,
            "is_squeeze_breakout": is_squeeze_breakout,
            "bandwidth_ratio": round(bandwidth_ratio, 2),
            "upper_slope": upper_slope,
            "lower_slope": lower_slope,
            "curr_upper": curr_upper,
            "curr_lower": curr_lower
        }
    except Exception as e:
        log_error(MODULE, f"Error detectando Squeeze Expansion: {e}")
        return {
            "is_expanding": False,
            "is_divergent": False,
            "was_compressed": False,
            "is_squeeze_breakout": False,
            "bandwidth_ratio": 1.0,
            "upper_slope": 0.0,
            "lower_slope": 0.0,
            "curr_upper": 0.0,
            "curr_lower": 0.0
        }

def check_triple_ema_alignment(df_5m: pd.DataFrame, direction: str) -> bool:
    """Verifica alineación de EMAs en 5m (EMA3, EMA9, EMA20)."""
    if df_5m is None or len(df_5m) < 20:
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

def calculate_5m_velocity(df_5m: pd.DataFrame) -> dict:
    """
    Calcula la velocidad y aceleración del mercado directamente en velas de 5m.
    Fórmula: V_5m = ((body_ratio + range_ratio) / 2.0) * volume_ratio
    Umbral de alta velocidad: V_5m >= 2.5
    """
    if df_5m is None or len(df_5m) < 20:
        return {"v_5m_score": 0.0, "is_high_velocity": False, "direction": "NEUTRAL", "volume_ratio": 1.0}

    try:
        last = df_5m.iloc[-1]
        c = float(last['close'])
        o = float(last['open'])
        h = float(last['high'])
        l = float(last['low'])
        body = abs(c - o)
        rng = h - l if (h - l) > 0 else 0.0001

        # Promedios de las últimas 20 velas de 5m
        bodies_20 = (df_5m['close'].iloc[-20:] - df_5m['open'].iloc[-20:]).abs()
        avg_body_5m = float(bodies_20.mean())
        if avg_body_5m <= 0:
            avg_body_5m = body if body > 0 else 0.0001

        ranges_20 = (df_5m['high'].iloc[-20:] - df_5m['low'].iloc[-20:])
        avg_range_5m = float(ranges_20.mean())
        if avg_range_5m <= 0:
            avg_range_5m = rng

        growth_ratio = body / avg_body_5m
        range_ratio = rng / avg_range_5m
        v_base = (growth_ratio + range_ratio) / 2.0

        # Ratio de volumen vs SMA20
        vol_curr = float(last.get('volume', 1.0))
        vol_sma20 = float(df_5m['volume'].iloc[-20:].mean()) if 'volume' in df_5m.columns else 1.0
        vol_ratio = vol_curr / vol_sma20 if vol_sma20 > 0 else 1.0

        v_5m = v_base * min(vol_ratio, 3.0)
        is_high_velocity = v_5m >= 2.5
        direction = "BEARISH_SURGE" if c < o else "BULLISH_SURGE"

        return {
            "v_5m_score": round(v_5m, 2),
            "is_high_velocity": is_high_velocity,
            "direction": direction,
            "growth_ratio": round(growth_ratio, 2),
            "range_ratio": round(range_ratio, 2),
            "volume_ratio": round(vol_ratio, 2)
        }
    except Exception as e:
        log_error(MODULE, f"Error calculando velocidad 5m: {e}")
        return {"v_5m_score": 0.0, "is_high_velocity": False, "direction": "NEUTRAL", "volume_ratio": 1.0}

def calculate_sipv_indicator(df_15m: pd.DataFrame) -> dict:
    """
    Sistema de Indicadores de Presión y Volumen (SIPV) en 15 MINUTOS.
    Detecta clímax de volumen institucional, absorción y agotamiento para la salida activa.
    """
    if df_15m is None or len(df_15m) < 14:
        return {
            "sipv_score": 0.0,
            "is_bullish_climax": False,
            "is_bearish_climax": False,
            "vol_ratio_15m": 1.0,
            "upper_wick_ratio": 0.0,
            "lower_wick_ratio": 0.0
        }

    try:
        last = df_15m.iloc[-1]
        c = float(last['close'])
        o = float(last['open'])
        h = float(last['high'])
        l = float(last['low'])
        rng = h - l if (h - l) > 0 else 0.0001

        upper_wick = h - max(c, o)
        lower_wick = min(c, o) - l
        body = abs(c - o)

        upper_wick_ratio = upper_wick / rng
        lower_wick_ratio = lower_wick / rng
        body_ratio = body / rng

        vol_curr = float(last.get('volume', 1.0))
        vol_sma20 = float(df_15m['volume'].iloc[-20:].mean()) if 'volume' in df_15m.columns else 1.0
        vol_ratio_15m = vol_curr / vol_sma20 if vol_sma20 > 0 else 1.0

        # Score SIPV de presión (-1.0 a +1.0) ponderado por volumen
        pressure_raw = ((c - l) / rng - 0.5) * 2.0
        sipv_score = pressure_raw * min(vol_ratio_15m, 3.0)

        # Clímax alcista: Alto volumen (>=2.0x) con mecha superior notable o rechazo
        is_bullish_climax = (vol_ratio_15m >= 2.0) and (upper_wick_ratio >= 0.35 or (body_ratio < 0.4 and c < h))

        # Clímax bajista: Alto volumen (>=2.0x) con mecha inferior notable o absorción compradora
        is_bearish_climax = (vol_ratio_15m >= 2.0) and (lower_wick_ratio >= 0.35 or (body_ratio < 0.4 and c > l))

        return {
            "sipv_score": round(sipv_score, 2),
            "is_bullish_climax": is_bullish_climax,
            "is_bearish_climax": is_bearish_climax,
            "vol_ratio_15m": round(vol_ratio_15m, 2),
            "upper_wick_ratio": round(upper_wick_ratio, 2),
            "lower_wick_ratio": round(lower_wick_ratio, 2)
        }
    except Exception as e:
        log_error(MODULE, f"Error calculando SIPV 15m: {e}")
        return {
            "sipv_score": 0.0,
            "is_bullish_climax": False,
            "is_bearish_climax": False,
            "vol_ratio_15m": 1.0,
            "upper_wick_ratio": 0.0,
            "lower_wick_ratio": 0.0
        }

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

def scan_squeeze_opportunities(
    symbol: str,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame = None,
    market_type: str = 'forex_futures'
) -> dict | None:
    """
    Scanner Multi-Par Autónomo QSHR v5.
    Evalúa si un símbolo presenta un Squeeze Breakout activo (LONG o SHORT)
    para ser enviado a validación en ADUANAS.
    """
    if df_5m is None or len(df_5m) < 20:
        return None

    try:
        last_5m = df_5m.iloc[-1]
        current_price = float(last_5m['close'])
        open_price = float(last_5m['open'])

        squeeze = detect_bollinger_squeeze_expansion(df_5m)
        if not squeeze['is_squeeze_breakout']:
            return None

        vel_info = calculate_5m_velocity(df_5m)
        if not vel_info['is_high_velocity']:
            return None

        # Anti-Fakeout: El cuerpo de la vela de 5m debe ser al menos 50% del rango total
        rng_5m = float(last_5m['high']) - float(last_5m['low'])
        body_5m = abs(current_price - open_price)
        if rng_5m > 0 and (body_5m / rng_5m) < 0.50:
            return None

        # 1. Ruptura Alcista Directa (LONG)
        if current_price >= squeeze['curr_upper'] and current_price > open_price:
            if check_triple_ema_alignment(df_5m, 'bullish') and vel_info['direction'] == 'BULLISH_SURGE':
                sl_price = calculate_hedge_sl(last_5m, 'long', symbol)
                return {
                    "action": "open_direct_long",
                    "side": "long",
                    "rule_code": "Bb33_QSHR_DIRECT_LONG",
                    "order_type": "MARKET",
                    "sl_price": sl_price,
                    "velocity": vel_info['v_5m_score'],
                    "bandwidth_ratio": squeeze['bandwidth_ratio'],
                    "reason": f"QSHR v5 Direct LONG: Squeeze Breakout 5m confirmado (V_5m={vel_info['v_5m_score']}, BB_Ratio={squeeze['bandwidth_ratio']})"
                }

        # 2. Ruptura Bajista Directa (SHORT)
        if current_price <= squeeze['curr_lower'] and current_price < open_price:
            if check_triple_ema_alignment(df_5m, 'bearish') and vel_info['direction'] == 'BEARISH_SURGE':
                sl_price = calculate_hedge_sl(last_5m, 'short', symbol)
                return {
                    "action": "open_direct_short",
                    "side": "short",
                    "rule_code": "Bb33_QSHR_DIRECT_SHORT",
                    "order_type": "MARKET",
                    "sl_price": sl_price,
                    "velocity": vel_info['v_5m_score'],
                    "bandwidth_ratio": squeeze['bandwidth_ratio'],
                    "reason": f"QSHR v5 Direct SHORT: Squeeze Breakout 5m confirmado (V_5m={vel_info['v_5m_score']}, BB_Ratio={squeeze['bandwidth_ratio']})"
                }

        return None
    except Exception as e:
        log_error(MODULE, f"Error escaneando oportunidades Squeeze {symbol}: {e}")
        return None

def detect_squeeze_pinch_charging(df_5m: pd.DataFrame) -> dict:
    """
    Detección de Pre-Compresión (Pinch Pre-Alert) antes de la ruptura.
    Identifica contracción severa del ancho de banda (bandwidth <= 70% del promedio de 20 períodos).
    """
    if df_5m is None or len(df_5m) < 20:
        return {"is_charging": False, "pinch_ratio": 1.0}

    try:
        upper_col = 'upper_1' if 'upper_1' in df_5m.columns else ('upper_bollinger' if 'upper_bollinger' in df_5m.columns else None)
        lower_col = 'lower_1' if 'lower_1' in df_5m.columns else ('lower_bollinger' if 'lower_bollinger' in df_5m.columns else None)

        if not upper_col or not lower_col:
            basis = df_5m['close'].rolling(20).mean()
            std = df_5m['close'].rolling(20).std()
            bandwidth = (basis + 2.0 * std) - (basis - 2.0 * std)
        else:
            bandwidth = df_5m[upper_col] - df_5m[lower_col]

        curr_bw = float(bandwidth.iloc[-1])
        avg_bw = float(bandwidth.iloc[-20:].mean()) if len(bandwidth) >= 20 else curr_bw
        pinch_ratio = curr_bw / avg_bw if avg_bw > 0 else 1.0
        is_charging = pinch_ratio <= 0.70

        return {"is_charging": is_charging, "pinch_ratio": round(pinch_ratio, 2)}
    except Exception as e:
        log_error(MODULE, f"Error calculando Pinch Pre-Alert: {e}")
        return {"is_charging": False, "pinch_ratio": 1.0}

def calculate_asymmetric_hedge_lots(orig_lots: float, v_5m_score: float, capital_multiplier: float = 1.0) -> float:
    """
    Calcula el lotaje de cobertura con multiplicador asimétrico acelerado (1.25x - 2.0x).
    Garantiza el respeto del tamaño mínimo permitido por el broker (0.01 lots en Forex).
    """
    base_lots = max(0.01, abs(float(orig_lots or 0.01)))
    if v_5m_score >= 3.0:
        mult = 1.5 * capital_multiplier
    elif v_5m_score >= 2.5:
        mult = 1.25 * capital_multiplier
    else:
        mult = 1.0

    calc_lots = round(base_lots * mult, 2)
    if base_lots == 0.01 and mult > 1.0:
        calc_lots = 0.02

    return max(0.01, round(calc_lots, 2))

def evaluate_qshr_trailing_and_exit(
    position: dict,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    current_price: float,
    symbol: str
) -> dict | None:
    """
    Evaluador unificado de salida "Ride & Close":
    1. Estrategia Activa: Salida Clímax por SIPV en 15m con soporte de Scale-Out (50% si lots >= 0.02).
    2. Niveles Fibonacci 15m: Reversión Cuántica Híbrida (50% Market + 50% Limit en Mecha).
    3. Estrategia Pasiva: Trailing stop siguiendo la EMA9 en 5m para el remanente.
    """
    if not position or df_5m is None or df_5m.empty:
        return None

    try:
        side = (position.get('side') or '').lower()
        pos_lots = abs(float(position.get('lots') or position.get('size') or 0.01))
        last_5m = df_5m.iloc[-1]
        c_5m = float(last_5m['close'])
        
        # EMA9 en 5m
        ema9_5m = float(last_5m.get('ma9') or last_5m.get('ema_9') or df_5m['close'].ewm(span=9, adjust=False).mean().iloc[-1])
        
        levels_15m = calculate_15m_fibonacci_levels(df_15m, current_price)
        sipv_15m = calculate_sipv_indicator(df_15m)
        vel_info = calculate_5m_velocity(df_5m)
        last_15m = df_15m.iloc[-1] if df_15m is not None and not df_15m.empty else last_5m
        high_15m = float(last_15m.get('high', current_price))
        low_15m = float(last_15m.get('low', current_price))

        # -------------------------------------------------------------
        # POSICIONES LONG
        # -------------------------------------------------------------
        if side in ('long', 'buy'):
            # 1. Estrategia Activa con Scale-Out (50% en SIPV Clímax si lots >= 0.02)
            if (current_price >= levels_15m['upper_band_15m'] or current_price >= levels_15m['upper_5_15m']) and sipv_15m['is_bullish_climax']:
                if pos_lots >= 0.02:
                    close_lots = round(pos_lots / 2.0, 2)
                    remaining_lots = round(pos_lots - close_lots, 2)
                    return {
                        "action": "partial_close_market_active_sipv",
                        "close_lots": close_lots,
                        "remaining_lots": remaining_lots,
                        "reason": f"QSHR Scale-Out 15m (50%): Clímax SIPV (Vol_15m={sipv_15m['vol_ratio_15m']}x). Cerrando {close_lots}L, dejando {remaining_lots}L en Trailing EMA9.",
                        "rule_code": "Bb33_QSHR_SIPV_SCALE_OUT"
                    }
                else:
                    return {
                        "action": "close_market_active_sipv",
                        "close_lots": pos_lots,
                        "reason": f"QSHR Active Exit 15m: Clímax SIPV detectado en sobre-extensión (Vol_15m={sipv_15m['vol_ratio_15m']}x, Wick={sipv_15m['upper_wick_ratio']})",
                        "rule_code": "Bb33_QSHR_SIPV_CLIMAX"
                    }

            # 2. Niveles Extremos de Fibonacci 15m (Reversión Cuántica Híbrida)
            if current_price >= levels_15m['upper_5_15m']:
                if current_price >= levels_15m['upper_6_15m']:
                    return {
                        "action": "reversal_at_level6",
                        "reversal_side": "short",
                        "reversal_type": "hybrid",
                        "limit_price": format_price_precision(symbol, high_15m),
                        "rule_code": "Bb33_QSHR_REVERSAL_L6_15M",
                        "reason": f"QSHR Reversal 15m Híbrido: Alcanzado Upper_6 ({levels_15m['upper_6_15m']:.5f}). Cerrar LONG e iniciar SHORT (Market + Limit en {high_15m:.5f})."
                    }
                else:
                    if vel_info['is_high_velocity'] and vel_info['direction'] == 'BULLISH_SURGE':
                        log_info(MODULE, f"🚀 [QSHR 15M ESCALATION] {symbol}: En Upper_5 ({levels_15m['upper_5_15m']:.5f}), V_5m={vel_info['v_5m_score']} ALTA. Escalando a Upper_6!")
                    else:
                        return {
                            "action": "reversal_at_level5",
                            "reversal_side": "short",
                            "reversal_type": "hybrid",
                            "limit_price": format_price_precision(symbol, high_15m),
                            "rule_code": "Bb33_QSHR_REVERSAL_L5_15M",
                            "reason": f"QSHR Reversal 15m Híbrido: Alcanzado Upper_5 ({levels_15m['upper_5_15m']:.5f}) con desaceleración. Cerrar LONG e iniciar SHORT."
                        }

            # 3. Estrategia Pasiva (Ruptura bajista de EMA9 en 5m)
            if c_5m < ema9_5m:
                return {
                    "action": "close_market_passive_ema9",
                    "close_lots": pos_lots,
                    "reason": f"QSHR Passive Exit 5m: Vela cerró bajo EMA9 ({c_5m:.5f} < {ema9_5m:.5f})",
                    "rule_code": "Bb33_QSHR_EMA9_TRAILING"
                }

        # -------------------------------------------------------------
        # POSICIONES SHORT
        # -------------------------------------------------------------
        elif side in ('short', 'sell'):
            # 1. Estrategia Activa con Scale-Out (50% en SIPV Clímax si lots >= 0.02)
            if (current_price <= levels_15m['lower_band_15m'] or current_price <= levels_15m['lower_5_15m']) and sipv_15m['is_bearish_climax']:
                if pos_lots >= 0.02:
                    close_lots = round(pos_lots / 2.0, 2)
                    remaining_lots = round(pos_lots - close_lots, 2)
                    return {
                        "action": "partial_close_market_active_sipv",
                        "close_lots": close_lots,
                        "remaining_lots": remaining_lots,
                        "reason": f"QSHR Scale-Out 15m (50%): Clímax SIPV bajista (Vol_15m={sipv_15m['vol_ratio_15m']}x). Cerrando {close_lots}L, dejando {remaining_lots}L en Trailing EMA9.",
                        "rule_code": "Bb33_QSHR_SIPV_SCALE_OUT"
                    }
                else:
                    return {
                        "action": "close_market_active_sipv",
                        "close_lots": pos_lots,
                        "reason": f"QSHR Active Exit 15m: Clímax SIPV detectado en sobre-extensión bajista (Vol_15m={sipv_15m['vol_ratio_15m']}x, Wick={sipv_15m['lower_wick_ratio']})",
                        "rule_code": "Bb33_QSHR_SIPV_CLIMAX"
                    }

            # 2. Niveles Extremos de Fibonacci 15m (Reversión Cuántica Híbrida)
            if current_price <= levels_15m['lower_5_15m']:
                if current_price <= levels_15m['lower_6_15m']:
                    return {
                        "action": "reversal_at_level6",
                        "reversal_side": "long",
                        "reversal_type": "hybrid",
                        "limit_price": format_price_precision(symbol, low_15m),
                        "rule_code": "Bb33_QSHR_REVERSAL_L6_15M",
                        "reason": f"QSHR Reversal 15m Híbrido: Alcanzado Lower_6 ({levels_15m['lower_6_15m']:.5f}). Cerrar SHORT e iniciar LONG (Market + Limit en {low_15m:.5f})."
                    }
                else:
                    if vel_info['is_high_velocity'] and vel_info['direction'] == 'BEARISH_SURGE':
                        log_info(MODULE, f"🚀 [QSHR 15M ESCALATION] {symbol}: En Lower_5 ({levels_15m['lower_5_15m']:.5f}), V_5m={vel_info['v_5m_score']} ALTA. Escalando a Lower_6!")
                    else:
                        return {
                            "action": "reversal_at_level5",
                            "reversal_side": "long",
                            "reversal_type": "hybrid",
                            "limit_price": format_price_precision(symbol, low_15m),
                            "rule_code": "Bb33_QSHR_REVERSAL_L5_15M",
                            "reason": f"QSHR Reversal 15m Híbrido: Alcanzado Lower_5 ({levels_15m['lower_5_15m']:.5f}) con desaceleración. Cerrar SHORT e iniciar LONG."
                        }

            # 3. Estrategia Pasiva (Ruptura alcista de EMA9 en 5m)
            if c_5m > ema9_5m:
                return {
                    "action": "close_market_passive_ema9",
                    "close_lots": pos_lots,
                    "reason": f"QSHR Passive Exit 5m: Vela cerró sobre EMA9 ({c_5m:.5f} > {ema9_5m:.5f})",
                    "rule_code": "Bb33_QSHR_EMA9_TRAILING"
                }

        return None
    except Exception as e:
        log_error(MODULE, f"Error evaluando trailing/exit QSHR {symbol}: {e}")
        return None

def evaluate_qshr_hedge_signal(
    symbol: str,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame = None,
    active_position: dict = None,
    market_type: str = 'forex_futures',
    capital_multiplier: float = 1.0
) -> dict | None:
    """
    Evaluador Principal QUANTUM SQUEEZE HEDGE & REVERSAL (Bb33_QSHR v5).
    Soporta Cobertura Asimétrica Acelerada (1.25x-2.0x) y Entrada Directa.
    """
    if df_5m is None or df_5m.empty or len(df_5m) < 20:
        return None

    try:
        last_5m = df_5m.iloc[-1]
        current_price = float(last_5m['close'])
        
        levels_15m = calculate_15m_fibonacci_levels(df_15m, current_price)
        squeeze = detect_bollinger_squeeze_expansion(df_5m)
        is_expanding = squeeze['is_expanding']
        vel_info = calculate_5m_velocity(df_5m)

        # MODO 1: RUPTURA DIRECTA (0 POSICIONES ACTIVAS)
        if not active_position:
            return scan_squeeze_opportunities(symbol, df_5m, df_15m, market_type)

        # MODO 2: COBERTURA ASIMÉTRICA Y GESTIÓN CON POSICIÓN ACTIVA
        orig_side = (active_position.get('side') or '').lower()
        orig_lots = abs(float(active_position.get('lots') or active_position.get('size') or 0.01))

        # CASO A: Posición Original es LONG
        if orig_side in ('long', 'buy'):
            has_hedge_short = active_position.get('has_hedge') or (active_position.get('rule_code') == 'Bb33_QSHR_HEDGE')
            is_bearish_breakout = (last_5m['close'] < last_5m['open']) and (current_price <= squeeze['curr_lower'])
            is_bullish_breakout = (last_5m['close'] > last_5m['open']) and (current_price >= squeeze['curr_upper'])

            # A0. TREND BOOSTER ALCISTA (Piramidación a Favor de LONG)
            if is_expanding and is_bullish_breakout and vel_info['is_high_velocity'] and vel_info['direction'] == 'BULLISH_SURGE':
                if check_triple_ema_alignment(df_5m, 'bullish'):
                    cluster_sl = calculate_cluster_stop_loss(symbol, last_5m, 'long')
                    return {
                        "action": "open_booster_long",
                        "side": "long",
                        "rule_code": "Bb33_QSHR_BOOSTER_LONG",
                        "order_type": "MARKET",
                        "sl_price": cluster_sl,
                        "velocity": vel_info['v_5m_score'],
                        "reason": f"QSHR Trend Booster LONG: Aceleración Squeeze a favor (V_5m={vel_info['v_5m_score']})"
                    }

            # A1. Cobertura Asimétrica Acelerada SHORT (1.25x - 2.0x)
            if is_expanding and is_bearish_breakout and not has_hedge_short:
                hedge_sl = calculate_hedge_sl(last_5m, 'short', symbol)
                asym_lots = calculate_asymmetric_hedge_lots(orig_lots, vel_info['v_5m_score'], capital_multiplier)
                return {
                    "action": "open_hedge_short",
                    "rule_code": "Bb33_QSHR_HEDGE",
                    "order_type": "MARKET",
                    "lots": asym_lots,
                    "sl_price": hedge_sl,
                    "reason": f"QSHR v5: Cobertura Asimétrica SHORT ({asym_lots}L) por Squeeze Expansion (V_5m={vel_info['v_5m_score']})"
                }

            # A2. Cierre de LONG Antigua por Filtro de 4 Factores
            ema_aligned_bearish = check_triple_ema_alignment(df_5m, 'bearish')
            at_lower_band = (current_price <= squeeze['curr_lower'])
            high_vel_bearish = vel_info['is_high_velocity'] and (vel_info['direction'] == 'BEARISH_SURGE')

            if ema_aligned_bearish and is_expanding and at_lower_band and high_vel_bearish:
                return {
                    "action": "close_original_long",
                    "rule_code": "Bb33_QSHR_EXIT",
                    "reason": f"QSHR Exit: 4 Factores validados (EMA3<9<20, Squeeze Exp, Lower Band 5m, V_5m={vel_info['v_5m_score']})"
                }

            # A3. Evaluación de Reversión y Extremos 15m
            return evaluate_qshr_trailing_and_exit(active_position, df_5m, df_15m, current_price, symbol)

        # CASO B: Posición Original es SHORT
        elif orig_side in ('short', 'sell'):
            has_hedge_long = active_position.get('has_hedge') or (active_position.get('rule_code') == 'Bb33_QSHR_HEDGE')
            is_bullish_breakout = (last_5m['close'] > last_5m['open']) and (current_price >= squeeze['curr_upper'])
            is_bearish_breakout = (last_5m['close'] < last_5m['open']) and (current_price <= squeeze['curr_lower'])

            # B0. TREND BOOSTER BAJISTA (Piramidación a Favor de SHORT)
            if is_expanding and is_bearish_breakout and vel_info['is_high_velocity'] and vel_info['direction'] == 'BEARISH_SURGE':
                if check_triple_ema_alignment(df_5m, 'bearish'):
                    cluster_sl = calculate_cluster_stop_loss(symbol, last_5m, 'short')
                    return {
                        "action": "open_booster_short",
                        "side": "short",
                        "rule_code": "Bb33_QSHR_BOOSTER_SHORT",
                        "order_type": "MARKET",
                        "sl_price": cluster_sl,
                        "velocity": vel_info['v_5m_score'],
                        "reason": f"QSHR Trend Booster SHORT: Aceleración Squeeze a favor (V_5m={vel_info['v_5m_score']})"
                    }

            # B1. Cobertura Asimétrica Acelerada LONG (1.25x - 2.0x)
            if is_expanding and is_bullish_breakout and not has_hedge_long:
                hedge_sl = calculate_hedge_sl(last_5m, 'long', symbol)
                asym_lots = calculate_asymmetric_hedge_lots(orig_lots, vel_info['v_5m_score'], capital_multiplier)
                return {
                    "action": "open_hedge_long",
                    "rule_code": "Bb33_QSHR_HEDGE",
                    "order_type": "MARKET",
                    "lots": asym_lots,
                    "sl_price": hedge_sl,
                    "reason": f"QSHR v5: Cobertura Asimétrica LONG ({asym_lots}L) por Squeeze Expansion (V_5m={vel_info['v_5m_score']})"
                }

            # B2. Cierre de SHORT Antigua por Filtro de 4 Factores
            ema_aligned_bullish = check_triple_ema_alignment(df_5m, 'bullish')
            at_upper_band = (current_price >= squeeze['curr_upper'])
            high_vel_bullish = vel_info['is_high_velocity'] and (vel_info['direction'] == 'BULLISH_SURGE')

            if ema_aligned_bullish and is_expanding and at_upper_band and high_vel_bullish:
                return {
                    "action": "close_original_short",
                    "rule_code": "Bb33_QSHR_EXIT",
                    "reason": f"QSHR Exit: 4 Factores validados (EMA3>9>20, Squeeze Exp, Upper Band 5m, V_5m={vel_info['v_5m_score']})"
                }

            # B3. Evaluación de Reversión y Extremos 15m
            return evaluate_qshr_trailing_and_exit(active_position, df_5m, df_15m, current_price, symbol)

        return None
    except Exception as e:
        log_error(MODULE, f"Error evaluando estrategia QSHR v5: {e}")
        return None

def calculate_cluster_stop_loss(symbol: str, breakout_candle: pd.Series, side: str, buffer_pips: float = 2.0) -> float:
    """
    Calcula el Stop Loss estructural sincronizado para todo el Cluster de posiciones del par.
    """
    is_jpy = 'JPY' in (symbol or '').upper()
    pip_factor = 0.01 if is_jpy else 0.0001

    if side.lower() in ('short', 'sell'):
        high_val = float(breakout_candle.get('high', 0))
        sl = high_val + (buffer_pips * pip_factor)
    else:
        low_val = float(breakout_candle.get('low', 0))
        sl = low_val - (buffer_pips * pip_factor)

    return format_price_precision(symbol, sl)

def evaluate_cluster_exit(
    symbol: str,
    active_positions: list[dict],
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    current_price: float
) -> dict | None:
    """
    Evalúa si se debe ejecutar un Take Profit en Bloque (Cluster Take Profit)
    para TODAS las posiciones activas en la misma dirección al alcanzar el clímax SIPV en 15m.
    """
    if not active_positions or df_15m is None or df_15m.empty:
        return None

    try:
        sipv = calculate_sipv_indicator(df_15m)
        levels_15m = calculate_15m_fibonacci_levels(df_15m, current_price)
        side = (active_positions[0].get('side') or '').lower()

        if side in ('long', 'buy'):
            if (current_price >= levels_15m['upper_5_15m'] or current_price >= levels_15m['upper_band_15m']) and sipv['is_bullish_climax']:
                return {
                    "action": "cluster_take_profit",
                    "side": "long",
                    "position_ids": [p.get('id') for p in active_positions if p.get('id')],
                    "rule_code": "Bb33_QSHR_CLUSTER_TP",
                    "reason": f"QSHR Cluster TP 15m: Clímax SIPV alcista en sobre-extensión ({len(active_positions)} posiciones cerradas)"
                }
        elif side in ('short', 'sell'):
            if (current_price <= levels_15m['lower_5_15m'] or current_price <= levels_15m['lower_band_15m']) and sipv['is_bearish_climax']:
                return {
                    "action": "cluster_take_profit",
                    "side": "short",
                    "position_ids": [p.get('id') for p in active_positions if p.get('id')],
                    "rule_code": "Bb33_QSHR_CLUSTER_TP",
                    "reason": f"QSHR Cluster TP 15m: Clímax SIPV bajista en sobre-extensión ({len(active_positions)} posiciones cerradas)"
                }

        return None
    except Exception as e:
        log_error(MODULE, f"Error evaluando cluster exit {symbol}: {e}")
        return None

def get_qshr_hud_status(symbol: str, df_5m: pd.DataFrame, df_15m: pd.DataFrame, active_position: dict = None) -> dict:
    """
    Retorna el estado de telemetría QSHR para el HUD visual del Frontend.
    """
    try:
        pinch = detect_squeeze_pinch_charging(df_5m)
        squeeze = detect_bollinger_squeeze_expansion(df_5m)
        vel = calculate_5m_velocity(df_5m)
        sipv = calculate_sipv_indicator(df_15m)
        
        has_pos = bool(active_position)
        is_hedge = active_position.get('rule_code') == 'Bb33_QSHR_HEDGE' if has_pos else False
        
        if is_hedge:
            state_label = "COBERTURA ACTIVA"
            state_badge = "HEDGE_ACTIVE"
            color = "#38BDF8"
        elif squeeze['is_squeeze_breakout']:
            state_label = f"RUPTURA ACTIVA (V: {vel['v_5m_score']})"
            state_badge = "BREAKOUT"
            color = "#00C896"
        elif sipv['is_bullish_climax'] or sipv['is_bearish_climax']:
            state_label = "CLÍMAX SIPV (15m)"
            state_badge = "CLIMAX_SIPV"
            color = "#EF4444"
        elif pinch['is_charging']:
            state_label = f"COMPRIMIENDO ({int(pinch['pinch_ratio']*100)}%)"
            state_badge = "PINCH_CHARGING"
            color = "#F59E0B"
        else:
            state_label = "NORMAL / MONITOREO"
            state_badge = "NEUTRAL"
            color = "#94A3B8"
            
        return {
            "symbol": symbol,
            "state_label": state_label,
            "state_badge": state_badge,
            "color": color,
            "v_5m_score": vel.get('v_5m_score', 0.0),
            "bandwidth_ratio": squeeze.get('bandwidth_ratio', 1.0),
            "pinch_ratio": pinch.get('pinch_ratio', 1.0),
            "sipv_score": sipv.get('sipv_score', 0.0),
            "vol_ratio_15m": sipv.get('vol_ratio_15m', 1.0)
        }
    except Exception as e:
        log_error(MODULE, f"Error obteniendo HUD status QSHR {symbol}: {e}")
        return {
            "symbol": symbol,
            "state_label": "MONITOREO",
            "state_badge": "NEUTRAL",
            "color": "#94A3B8",
            "v_5m_score": 0.0,
            "bandwidth_ratio": 1.0,
            "pinch_ratio": 1.0,
            "sipv_score": 0.0,
            "vol_ratio_15m": 1.0
        }


