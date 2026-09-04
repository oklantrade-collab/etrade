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
from app.cascada.level_evaluator import check_fib_zone_reversal_15m, calculate_fib_exhaustion_velocity

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

        # Niveles Fibonacci estándar 1..4
        upper_1 = float(last.get('upper_1') or (basis + (0.236 * 3.0 * std)))
        upper_2 = float(last.get('upper_2') or (basis + (0.382 * 3.0 * std)))
        upper_3 = float(last.get('upper_3') or (basis + (0.500 * 3.0 * std)))
        upper_4 = float(last.get('upper_4') or (basis + (0.618 * 3.0 * std)))
        
        lower_1 = float(last.get('lower_1') or (basis - (0.236 * 3.0 * std)))
        lower_2 = float(last.get('lower_2') or (basis - (0.382 * 3.0 * std)))
        lower_3 = float(last.get('lower_3') or (basis - (0.500 * 3.0 * std)))
        lower_4 = float(last.get('lower_4') or (basis - (0.618 * 3.0 * std)))

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
            "upper_1": upper_1,
            "upper_2": upper_2,
            "upper_3": upper_3,
            "upper_4": upper_4,
            "upper_5_15m": upper_5_15m,
            "upper_6_15m": upper_6_15m,
            "lower_1": lower_1,
            "lower_2": lower_2,
            "lower_3": lower_3,
            "lower_4": lower_4,
            "lower_5_15m": lower_5_15m,
            "lower_6_15m": lower_6_15m,
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
    Detecta si las Bandas de Bollinger estándar (20 periodos, 2.0 std) presentan compresión previa y expansión divergente activa.
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
        c = df_5m['close']
        basis = c.rolling(20, min_periods=1).mean()
        std = c.rolling(20, min_periods=1).std().fillna(0)
        upper_series = basis + (2.0 * std)
        lower_series = basis - (2.0 * std)

        curr_upper = float(upper_series.iloc[-1])
        prev_upper = float(upper_series.iloc[-2]) if len(upper_series) > 1 else curr_upper
        curr_lower = float(lower_series.iloc[-1])
        prev_lower = float(lower_series.iloc[-2]) if len(lower_series) > 1 else curr_lower

        bandwidth_series = upper_series - lower_series
        curr_bandwidth = float(bandwidth_series.iloc[-1])
        prev_bandwidth = float(bandwidth_series.iloc[-2]) if len(bandwidth_series) > 1 else curr_bandwidth
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

def check_15m_anti_range_filter(df_15m: pd.DataFrame, current_price: float, side: str, v_5m_score: float = 0.0) -> dict:
    """
    Filtro Anti-Rango 15m para Squeeze en 5m:
    Evita comprar en la resistencia (techo) o vender en el soporte (piso) de un canal lateral de 15m.
    
    Lógica Cuantitativa:
    - Posición relativa en canal BB 15m: bb_pos_pct = (current_price - lower_15m) / (upper_15m - lower_15m)
    - Si las bandas de 15m están planas o sin expansión activa (bandwidth_ratio_15m < 1.15):
      * LONG: Si bb_pos_pct >= 0.80 (techo de 15m) y V_5m < 3.0: BLOQUEADO (15M_RANGE_RESISTANCE_BLOCKED).
        Si V_5m >= 3.0 pero current_price < upper_15m: BLOQUEADO hasta rotura real.
      * SHORT: Si bb_pos_pct <= 0.20 (piso de 15m) y V_5m < 3.0: BLOQUEADO (15M_RANGE_SUPPORT_BLOCKED).
        Si V_5m >= 3.0 pero current_price > lower_15m: BLOQUEADO hasta rotura real.
    """
    if df_15m is None or len(df_15m) < 20:
        return {"passed": True, "reason": "No 15m data, filter bypassed"}

    try:
        upper_col = 'upper_1' if 'upper_1' in df_15m.columns else ('upper_bollinger' if 'upper_bollinger' in df_15m.columns else None)
        lower_col = 'lower_1' if 'lower_1' in df_15m.columns else ('lower_bollinger' if 'lower_bollinger' in df_15m.columns else None)

        if not upper_col or not lower_col:
            basis_15m = df_15m['close'].rolling(20).mean()
            std_15m = df_15m['close'].rolling(20).std()
            upper_series = basis_15m + 2.0 * std_15m
            lower_series = basis_15m - 2.0 * std_15m
        else:
            upper_series = df_15m[upper_col]
            lower_series = df_15m[lower_col]

        curr_upper = float(upper_series.iloc[-1])
        curr_lower = float(lower_series.iloc[-1])
        bb_range = curr_upper - curr_lower
        if bb_range <= 0:
            return {"passed": True, "reason": "Zero 15m BB range"}

        bb_pos_pct = (current_price - curr_lower) / bb_range

        bw_series = upper_series - lower_series
        curr_bw = float(bw_series.iloc[-1])
        avg_bw_20 = float(bw_series.iloc[-20:].mean()) if len(bw_series) >= 20 else curr_bw
        bw_ratio_15m = curr_bw / avg_bw_20 if avg_bw_20 > 0 else 1.0

        prev_upper = float(upper_series.iloc[-2]) if len(upper_series) >= 2 else curr_upper
        prev_lower = float(lower_series.iloc[-2]) if len(lower_series) >= 2 else curr_lower
        upper_slope = curr_upper - prev_upper
        lower_slope = curr_lower - prev_lower

        is_15m_expanding = (bw_ratio_15m >= 1.15) or (upper_slope > 0 and lower_slope < 0)

        side_norm = side.lower()
        if side_norm in ('long', 'buy'):
            if bb_pos_pct >= 0.80 and not is_15m_expanding:
                if v_5m_score < 3.0:
                    return {
                        "passed": False,
                        "rule_triggered": "15M_RANGE_RESISTANCE_BLOCKED",
                        "bb_pos_pct": round(bb_pos_pct * 100, 1),
                        "reason": f"LONG Bloqueado por Anti-Rango 15m: Precio en techo ({bb_pos_pct*100:.1f}%) con BB 15m planas (Ratio={bw_ratio_15m:.2f}, V_5m={v_5m_score:.2f} < 3.0)"
                    }
                elif current_price < curr_upper:
                    return {
                        "passed": False,
                        "rule_triggered": "15M_RANGE_RESISTANCE_BLOCKED",
                        "bb_pos_pct": round(bb_pos_pct * 100, 1),
                        "reason": f"LONG Bloqueado por Anti-Rango 15m: Resistencia 15m sin rotura confirmada (Price={current_price:.5f} < Upper={curr_upper:.5f})"
                    }

        elif side_norm in ('short', 'sell'):
            if bb_pos_pct <= 0.20 and not is_15m_expanding:
                if v_5m_score < 3.0:
                    return {
                        "passed": False,
                        "rule_triggered": "15M_RANGE_SUPPORT_BLOCKED",
                        "bb_pos_pct": round(bb_pos_pct * 100, 1),
                        "reason": f"SHORT Bloqueado por Anti-Rango 15m: Precio en piso ({bb_pos_pct*100:.1f}%) con BB 15m planas (Ratio={bw_ratio_15m:.2f}, V_5m={v_5m_score:.2f} < 3.0)"
                    }
                elif current_price > curr_lower:
                    return {
                        "passed": False,
                        "rule_triggered": "15M_RANGE_SUPPORT_BLOCKED",
                        "bb_pos_pct": round(bb_pos_pct * 100, 1),
                        "reason": f"SHORT Bloqueado por Anti-Rango 15m: Soporte 15m sin rotura confirmada (Price={current_price:.5f} > Lower={curr_lower:.5f})"
                    }

        return {"passed": True, "bb_pos_pct": round(bb_pos_pct * 100, 1), "reason": "15m Anti-Range filter passed"}
    except Exception as e:
        log_error(MODULE, f"Error evaluando 15m Anti-Range filter: {e}")
        return {"passed": True, "reason": f"Error: {e}"}

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

def calculate_5m_velocity(df_5m: pd.DataFrame, market_type: str = 'crypto_futures', symbol: str = '') -> dict:
    """
    Calcula la velocidad y aceleración del mercado directamente en velas de 5m con umbral adaptativo (Crypto vs Forex).
    Fórmula: V_5m = ((body_ratio + range_ratio) / 2.0) * volume_ratio
    Umbrales:
      - Crypto: V_5m >= 3.0 (Alta aceleración / inyección de libro)
      - Forex:  V_5m >= 2.5 o desplazamiento >= 1.5 * ATR_5m
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

        # ── UMBRAL ADAPTATIVO (Mejora 3: Crypto vs Forex) ──
        is_crypto = 'crypto' in (market_type or '').lower() or 'USDT' in (symbol or '').upper()
        if is_crypto:
            is_high_velocity = v_5m >= 3.0 or (v_5m >= 2.5 and vol_ratio >= 2.0)
        else:
            # Forex: considerar también ATR displacement
            is_high_velocity = v_5m >= 2.5 or (avg_range_5m > 0 and rng >= 1.5 * avg_range_5m)

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

def evaluate_fullspan_velocity_breakout(
    symbol: str,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame = None,
    current_price: float = 0.0,
    market_type: str = 'crypto_futures'
) -> dict | None:
    """
    Regla Bb33_QSHR_FULLSPAN: Captura movimientos direccionales violentos en punto cero (Full-Span Breakdown/Breakout).
    
    Condiciones Clave:
    1. SHORT (Flash Dump):
       - Open_5m >= EMA20_5m (o Basis_5m)
       - Current_Price <= Lower_BB_5m
       - Aceleración (Condición OR): V_5m >= 3.0 (Crypto) / 2.5 (Forex) OR Expansión Divergente BB (Upper_Slope > 0 y Lower_Slope < 0)
       - Mejora 1 (Anti-Mecha de Absorción): Precio en el 15% inferior de la vela (Current_Price <= Low + 0.15 * Range)
       - Mejora 2 (Anti-Agotamiento): Extensión de vela <= 2.5 * ATR_15m
    
    2. LONG (Flash Pump / Squeeze):
       - Open_5m <= EMA20_5m (o Basis_5m)
       - Current_Price >= Upper_BB_5m
       - Aceleración (Condición OR): V_5m >= 3.0 (Crypto) / 2.5 (Forex) OR Expansión Divergente BB (Upper_Slope > 0 y Lower_Slope < 0)
       - Mejora 1 (Anti-Mecha de Absorción): Precio en el 15% superior de la vela (Current_Price >= High - 0.15 * Range)
       - Mejora 2 (Anti-Agotamiento): Extensión de vela <= 2.5 * ATR_15m
    """
    if df_5m is None or len(df_5m) < 20:
        return None

    try:
        last_5m = df_5m.iloc[-1]
        c = float(current_price or last_5m['close'])
        o = float(last_5m['open'])
        h = float(last_5m['high'])
        l = float(last_5m['low'])
        rng_5m = h - l if (h - l) > 0 else 0.0001

        # Bollinger 5m
        c_series = df_5m['close']
        basis_5m = float(last_5m.get('basis') or c_series.rolling(20, min_periods=1).mean().iloc[-1])
        std_5m = float(c_series.rolling(20, min_periods=1).std().iloc[-1]) or (basis_5m * 0.002)
        upper_bb_5m = float(last_5m.get('upper_1') or last_5m.get('upper_bollinger') or (basis_5m + 2.0 * std_5m))
        lower_bb_5m = float(last_5m.get('lower_1') or last_5m.get('lower_bollinger') or (basis_5m - 2.0 * std_5m))

        # EMA20 5m
        ema20_5m = float(last_5m.get('ema20') or c_series.ewm(span=20, adjust=False).mean().iloc[-1])
        mean_reference = max(basis_5m, ema20_5m) if c < o else min(basis_5m, ema20_5m)

        # Expansión de bandas y velocidad
        squeeze_5m = detect_bollinger_squeeze_expansion(df_5m)
        is_divergent = squeeze_5m.get('is_divergent', False)
        vel_info = calculate_5m_velocity(df_5m, market_type=market_type, symbol=symbol)
        v_score = float(vel_info.get('v_5m_score', 0.0))
        is_high_velocity = vel_info.get('is_high_velocity', False)

        # Condición OR de Aceleración: Alta Velocidad V_5m >= 3.0 (o 2.5 Forex) OR Bandas Divergentes
        passes_acceleration_or = is_high_velocity or is_divergent or (squeeze_5m.get('bandwidth_ratio', 1.0) >= 1.25)

        # ATR 15m para Escudo Anti-Agotamiento (Mejora 2)
        atr_15m = 0.0010
        if df_15m is not None and len(df_15m) >= 14:
            tr_15m = np.maximum(df_15m['high'] - df_15m['low'], np.maximum(abs(df_15m['high'] - df_15m['close'].shift(1)), abs(df_15m['low'] - df_15m['close'].shift(1))))
            atr_15m = float(tr_15m.rolling(14, min_periods=1).mean().iloc[-1]) or (c * 0.005)
        else:
            atr_15m = rng_5m * 1.5

        # ── 1. EVALUACIÓN FULLSPAN SHORT (Flash Dump) ──
        # Nació en o sobre la media móvil/basis y perforó la banda inferior en la misma vela
        if o >= (mean_reference * 0.999) and c <= lower_bb_5m and passes_acceleration_or:
            # Mejora 1: Anti-Mecha de Absorción (Precio en el 15% inferior de la vela)
            max_allowed_rebound_price = l + (0.15 * rng_5m)
            passes_anti_wick = c <= max_allowed_rebound_price or (rng_5m > 0 and (h - c) / rng_5m >= 0.80)

            if passes_anti_wick:
                # Mejora 2: Escudo Anti-Agotamiento (Climax Guard)
                is_exhausted = rng_5m > (2.5 * atr_15m)
                order_type = "LIMIT" if is_exhausted else "MARKET"
                limit_entry = (h - (0.382 * rng_5m)) if is_exhausted else c
                sl_price = calculate_hedge_sl(last_5m, 'short', symbol)

                log_info(MODULE, f"⚡ [FULLSPAN VELOCITY SHORT] {symbol} detectado: Open={o:.4f} >= Mean={mean_reference:.4f}, Close={c:.4f} <= LowerBB={lower_bb_5m:.4f} (V_5m={v_score:.2f}, Type={order_type})")
                return {
                    "action": "open_fullspan_velocity_short",
                    "side": "short",
                    "rule_code": "Bb33_QSHR_FULLSPAN_SHORT",
                    "order_type": order_type,
                    "entry_price": limit_entry,
                    "sl_price": sl_price,
                    "velocity": v_score,
                    "bandwidth_ratio": squeeze_5m.get('bandwidth_ratio', 1.0),
                    "reason": f"QSHR FullSpan SHORT: Open>=EMA20 con rotura Lower BB y aceleración V_5m={v_score:.2f} (OR BB Divergence)"
                }

        # ── 2. EVALUACIÓN FULLSPAN LONG (Flash Pump / Short Squeeze) ──
        # Nació en o bajo la media móvil/basis y perforó la banda superior en la misma vela
        if o <= (mean_reference * 1.001) and c >= upper_bb_5m and passes_acceleration_or:
            # Mejora 1: Anti-Mecha de Absorción (Precio en el 15% superior de la vela)
            min_allowed_push_price = h - (0.15 * rng_5m)
            passes_anti_wick = c >= min_allowed_push_price or (rng_5m > 0 and (c - l) / rng_5m >= 0.80)

            if passes_anti_wick:
                # Mejora 2: Escudo Anti-Agotamiento (Climax Guard)
                is_exhausted = rng_5m > (2.5 * atr_15m)
                order_type = "LIMIT" if is_exhausted else "MARKET"
                limit_entry = (l + (0.382 * rng_5m)) if is_exhausted else c
                sl_price = calculate_hedge_sl(last_5m, 'long', symbol)

                log_info(MODULE, f"⚡ [FULLSPAN VELOCITY LONG] {symbol} detectado: Open={o:.4f} <= Mean={mean_reference:.4f}, Close={c:.4f} >= UpperBB={upper_bb_5m:.4f} (V_5m={v_score:.2f}, Type={order_type})")
                return {
                    "action": "open_fullspan_velocity_long",
                    "side": "long",
                    "rule_code": "Bb33_QSHR_FULLSPAN_LONG",
                    "order_type": order_type,
                    "entry_price": limit_entry,
                    "sl_price": sl_price,
                    "velocity": v_score,
                    "bandwidth_ratio": squeeze_5m.get('bandwidth_ratio', 1.0),
                    "reason": f"QSHR FullSpan LONG: Open<=EMA20 con rotura Upper BB y aceleración V_5m={v_score:.2f} (OR BB Divergence)"
                }

    except Exception as e:
        log_error(MODULE, f"Error evaluando FullSpan Velocity Breakout para {symbol}: {e}")

    return None

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
    Evalúa si un símbolo presenta un Squeeze Breakout activo, Momentum o Clímax
    condicionado a la confirmación de expansión de Bandas de Bollinger en 15 minutos.
    """
    if df_5m is None or len(df_5m) < 20:
        return None

    try:
        last_5m = df_5m.iloc[-1]
        current_price = float(last_5m['close'])
        open_price = float(last_5m['open'])

        # ─── 0. TOP PRIORITY: FULLSPAN VELOCITY BREAKOUT (Mejora Instantánea Punto Cero) ───
        fullspan_res = evaluate_fullspan_velocity_breakout(symbol, df_5m, df_15m, current_price, market_type)
        if fullspan_res:
            return fullspan_res

        squeeze = detect_bollinger_squeeze_expansion(df_5m)
        vel_info = calculate_5m_velocity(df_5m, market_type=market_type, symbol=symbol)
        v_score = float(vel_info.get('v_5m_score', 0.0))

        # ─── FILTRO MAESTRO: Expansión de Bandas de Bollinger en 15m (con Bypass por Alta Velocidad) ───
        # Si la velocidad extrema V_5m >= 3.0 está activa, se autoriza bypass del cálculo rezagado de 15m
        if df_15m is not None and len(df_15m) >= 20:
            squeeze_15m = detect_bollinger_squeeze_expansion(df_15m)
            is_15m_expanding = squeeze_15m['is_expanding'] or (squeeze_15m['bandwidth_ratio'] >= 1.15) or (v_score >= 3.0)
            if not is_15m_expanding:
                return None
        elif df_15m is not None and len(df_15m) < 20 and v_score < 3.0:
            return None

        # Squeeze breakout 5m: compresión previa, expansión divergente, o expansión activa con alta velocidad
        is_breakout_active = squeeze['is_squeeze_breakout'] or squeeze['is_expanding'] or (squeeze['bandwidth_ratio'] >= 1.15) or (v_score >= 3.0)

        # Anti-Fakeout adaptativo según velocidad y mercado:
        # Alta velocidad institucional (V_5m >= 4.0): 25% de cuerpo suficiente (captura velas BTC con mecha)
        # Velocidad estándar (V_5m >= 2.5): 30% para Crypto, 35% para Forex
        is_crypto = 'crypto' in market_type.lower() or 'USDT' in symbol.upper()
        if v_score >= 4.0:
            min_body_ratio = 0.25
        elif is_crypto:
            min_body_ratio = 0.30
        else:
            min_body_ratio = 0.35

        rng_5m = float(last_5m['high']) - float(last_5m['low'])
        body_5m = abs(current_price - open_price)
        passes_body_ratio = not (rng_5m > 0 and (body_5m / rng_5m) < min_body_ratio)

        # 1. Ruptura Alcista Directa (LONG)
        if vel_info['is_high_velocity'] and is_breakout_active and passes_body_ratio:
            if current_price >= squeeze['curr_upper'] and current_price > open_price:
                if check_triple_ema_alignment(df_5m, 'bullish') and vel_info['direction'] == 'BULLISH_SURGE':
                    # Filtro Anti-Rango 15m
                    if df_15m is not None:
                        anti_range = check_15m_anti_range_filter(df_15m, current_price, 'long', vel_info['v_5m_score'])
                        if not anti_range.get('passed', True):
                            log_info(MODULE, f"🛡️ [ANTI-RANGO 15M] {symbol} Direct LONG rechazado: {anti_range.get('reason')}")
                        else:
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
        if vel_info['is_high_velocity'] and is_breakout_active and passes_body_ratio:
            if current_price <= squeeze['curr_lower'] and current_price < open_price:
                if check_triple_ema_alignment(df_5m, 'bearish') and vel_info['direction'] == 'BEARISH_SURGE':
                    # Filtro Anti-Rango 15m
                    if df_15m is not None:
                        anti_range = check_15m_anti_range_filter(df_15m, current_price, 'short', vel_info['v_5m_score'])
                        if not anti_range.get('passed', True):
                            log_info(MODULE, f"🛡️ [ANTI-RANGO 15M] {symbol} Direct SHORT rechazado: {anti_range.get('reason')}")
                        else:
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

        # 3. MOMENTUM CASCADE (EMA3 vs EMA9 + Velocidad V_5m >= 2.0)
        # Permite capturar tendencias fuertes sin requerir compresión previa de 5m
        if v_score >= 2.0:
            ema3_5m = float(last_5m.get('ma3', 0) or last_5m.get('ema1', 0) or 0)
            ema9_5m = float(last_5m.get('ma9', 0) or last_5m.get('ema2', 0) or 0)
            
            if ema3_5m == 0.0 or ema9_5m == 0.0:
                c_5m = df_5m['close']
                ema3_5m = float(c_5m.ewm(span=3, adjust=False).mean().iloc[-1])
                ema9_5m = float(c_5m.ewm(span=9, adjust=False).mean().iloc[-1])

            # Momentum SHORT: EMA3 < EMA9 con impulso bajista y V_5m >= 2.0
            if ema3_5m < ema9_5m and (vel_info['direction'] == 'BEARISH_SURGE' or current_price < open_price):
                sl_price = calculate_hedge_sl(last_5m, 'short', symbol)
                return {
                    "action": "open_momentum_short",
                    "side": "short",
                    "rule_code": "Bb33_QSHR_MOMENTUM_SHORT",
                    "order_type": "MARKET",
                    "sl_price": sl_price,
                    "velocity": vel_info['v_5m_score'],
                    "bandwidth_ratio": squeeze['bandwidth_ratio'],
                    "reason": f"QSHR v5 Momentum SHORT: EMA3<EMA9 con V_5m={vel_info['v_5m_score']:.2f} >= 2.0"
                }

            # Momentum LONG: EMA3 > EMA9 con impulso alcista y V_5m >= 2.0
            if ema3_5m > ema9_5m and (vel_info['direction'] == 'BULLISH_SURGE' or current_price > open_price):
                sl_price = calculate_hedge_sl(last_5m, 'long', symbol)
                return {
                    "action": "open_momentum_long",
                    "side": "long",
                    "rule_code": "Bb33_QSHR_MOMENTUM_LONG",
                    "order_type": "MARKET",
                    "sl_price": sl_price,
                    "velocity": vel_info['v_5m_score'],
                    "bandwidth_ratio": squeeze['bandwidth_ratio'],
                    "reason": f"QSHR v5 Momentum LONG: EMA3>EMA9 con V_5m={vel_info['v_5m_score']:.2f} >= 2.0"
                }

        # 4. CLÍMAX EXTREMO FIBONACCI / SIPV (Toque de LOWER_6 / UPPER_6)
        # Reversión cuántica inmediata por agotamiento extremo de presión vendedora/compradora
        if df_15m is not None and len(df_15m) >= 2:
            last_15m = df_15m.iloc[-1]
            fib_zone = float(last_15m.get('fibonacci_zone', 0.0) or 0.0)
            l6_15m = float(last_15m.get('lower_6', 0.0) or 0.0)
            u6_15m = float(last_15m.get('upper_6', 0.0) or 0.0)
            rng_15m = float(last_15m.get('high', 0)) - float(last_15m.get('low', 0))
            low_15m = float(last_15m.get('low', 0))
            high_15m = float(last_15m.get('high', 0))
            c_15m = float(last_15m.get('close', 0))
            o_15m = float(last_15m.get('open', 0))

            # Clímax Bajista / Reversión LONG: Precio penetró LOWER_6 (o zona <= -5) y deja absorción
            touched_lower_extreme = (fib_zone <= -5) or (l6_15m > 0 and low_15m <= l6_15m)
            if touched_lower_extreme and rng_15m > 0:
                lower_wick_ratio = (min(c_15m, o_15m) - low_15m) / rng_15m
                # Mecha de absorción >= 30% o vela de rechazo con cierre verde/alto
                if lower_wick_ratio >= 0.30 or c_15m > o_15m:
                    sl_price = calculate_hedge_sl(last_5m, 'long', symbol)
                    return {
                        "action": "open_climax_reversal_long",
                        "side": "long",
                        "rule_code": "Bb33_QSHR_CLIMAX_LOWER6_LONG",
                        "order_type": "MARKET",
                        "sl_price": sl_price,
                        "velocity": vel_info['v_5m_score'],
                        "bandwidth_ratio": squeeze['bandwidth_ratio'],
                        "reason": f"QSHR v5 Clímax LOWER_6 LONG: Toque zona extrema (Fib {fib_zone}) con absorción SIPV ({lower_wick_ratio*100:.0f}% mecha)"
                    }

            # Clímax Alcista / Reversión SHORT: Precio penetró UPPER_6 (o zona >= 5) y deja absorción
            touched_upper_extreme = (fib_zone >= 5) or (u6_15m > 0 and high_15m >= u6_15m)
            if touched_upper_extreme and rng_15m > 0:
                upper_wick_ratio = (high_15m - max(c_15m, o_15m)) / rng_15m
                if upper_wick_ratio >= 0.30 or c_15m < o_15m:
                    sl_price = calculate_hedge_sl(last_5m, 'short', symbol)
                    return {
                        "action": "open_climax_reversal_short",
                        "side": "short",
                        "rule_code": "Bb33_QSHR_CLIMAX_UPPER6_SHORT",
                        "order_type": "MARKET",
                        "sl_price": sl_price,
                        "velocity": vel_info['v_5m_score'],
                        "bandwidth_ratio": squeeze['bandwidth_ratio'],
                        "reason": f"QSHR v5 Clímax UPPER_6 SHORT: Toque zona extrema (Fib {fib_zone}) con absorción SIPV ({upper_wick_ratio*100:.0f}% mecha)"
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

def get_fib_buffer_pct(symbol: str) -> float:
    """
    Retorna el buffer porcentual de seguridad para el Stop Loss Virtual Fibonacci
    según el tipo de activo. Este margen evita que testeos saludables de la banda
    activen el cierre virtual prematuramente.
    """
    s = (symbol or '').upper()
    if 'USDT' in s or 'USDC' in s:
        return 0.0020  # 0.20% para Crypto (BTC, ETH, SOL)
    elif 'XAU' in s or 'GOLD' in s:
        return 0.0012  # 0.12% para Oro (alta volatilidad)
    elif 'JPY' in s:
        return 0.0010  # 0.10% para JPY (spread más amplio)
    elif 'GBP' in s:
        return 0.0010  # 0.10% para GBP (spread más amplio)
    else:
        return 0.0008  # 0.08% para EURUSD y otros pares estándar

def evaluate_fib_band_virtual_sl(
    position: dict,
    df_15m: pd.DataFrame,
    current_price: float,
    symbol: str
) -> dict | None:
    """
    Stop Loss Virtual Reactivo anclado a Bandas de Fibonacci 15m.
    
    Funciona para LONG y SHORT, Crypto y Forex.
    El broker NO tiene este SL — es 100% controlado por eTrade.
    
    Para LONG:
      - Determina la banda Fibonacci inferior activa (Fib_Floor) según la posición del precio.
      - Si el precio cae por debajo de Fib_Floor * (1 - Buffer%) → cierre virtual inmediato.
    
    Para SHORT:
      - Determina la banda Fibonacci superior activa (Fib_Ceiling) según la posición del precio.
      - Si el precio sube por encima de Fib_Ceiling * (1 + Buffer%) → cierre virtual inmediato.
    """
    if not position or df_15m is None or len(df_15m) < 20:
        return None
    
    try:
        side = (position.get('side') or '').lower()
        entry_price = float(position.get('avg_entry_price') or position.get('entry_price') or current_price)
        pos_lots = abs(float(position.get('lots') or position.get('size') or position.get('shares') or 0.01))
        
        # Calcular niveles de Fibonacci de 15m
        levels = calculate_15m_fibonacci_levels(df_15m, current_price)
        basis = levels['basis_15m']
        buffer_pct = get_fib_buffer_pct(symbol)
        
        # Calcular EMA3 y EMA9 de 15m para validación de momento
        c15 = df_15m['close'] if 'close' in df_15m.columns else df_15m.get('c', pd.Series())
        ema3_15m = float(c15.ewm(span=3, adjust=False).mean().iloc[-1]) if len(c15) >= 10 else 0.0
        ema9_15m = float(c15.ewm(span=9, adjust=False).mean().iloc[-1]) if len(c15) >= 10 else 0.0

        # ─── POSICIONES LONG ───
        if side in ('long', 'buy'):
            # Solo activar si la posición está en drawdown (precio < entry)
            if current_price >= entry_price:
                return None
            
            # REGLA MAESTRA 15M: NUNCA ejecutar Stop Loss Virtual de LONG si EMA3 > EMA9 en 15m (momento alcista activo)
            if ema3_15m > 0 and ema9_15m > 0 and ema3_15m > ema9_15m:
                return None
            
            # Determinar la banda Fibonacci inferior activa según la zona de entrada
            # Se usa la banda inmediatamente inferior a donde se abrió la posición
            lower_1 = levels.get('lower_1', basis)
            lower_2 = levels.get('lower_2', lower_1)
            lower_3 = levels.get('lower_3', lower_2)
            lower_4 = levels.get('lower_4', lower_3)
            lower_band = levels.get('lower_band_15m', basis)
            
            # Seleccionar el piso Fibonacci protector según la posición del entry_price
            if entry_price >= levels.get('upper_1', basis):
                fib_floor = basis
            elif entry_price >= basis:
                fib_floor = lower_1
            elif entry_price >= lower_1:
                fib_floor = lower_2
            elif entry_price >= lower_2:
                fib_floor = lower_3
            elif entry_price >= lower_3:
                fib_floor = lower_4
            else:
                fib_floor = lower_band
            
            # Aplicar el buffer porcentual de seguridad por debajo de la banda
            sl_virtual_level = fib_floor * (1.0 - buffer_pct)
            
            if current_price <= sl_virtual_level:
                loss_pct = ((entry_price - current_price) / entry_price) * 100
                return {
                    "action": "close_virtual_fib_sl",
                    "close_lots": pos_lots,
                    "sl_virtual_level": format_price_precision(symbol, sl_virtual_level),
                    "fib_floor": format_price_precision(symbol, fib_floor),
                    "buffer_pct": buffer_pct * 100,
                    "rule_code": "Bb33_QSHR_FIB_VIRTUAL_SL",
                    "reason": (
                        f"SL Virtual Fibonacci LONG: Precio ({current_price:.5f}) perforó "
                        f"Fib Floor ({fib_floor:.5f}) con buffer {buffer_pct*100:.2f}% "
                        f"(SL Virtual: {sl_virtual_level:.5f}, EMA3_15m={ema3_15m:.5f} < EMA9_15m={ema9_15m:.5f}). Pérdida: -{loss_pct:.2f}%"
                    )
                }
        
        # ─── POSICIONES SHORT ───
        elif side in ('short', 'sell'):
            # Solo activar si la posición está en drawdown (precio > entry)
            if current_price <= entry_price:
                return None
            
            # REGLA MAESTRA 15M: NUNCA ejecutar Stop Loss Virtual de SHORT si EMA3 < EMA9 en 15m (momento bajista activo)
            if ema3_15m > 0 and ema9_15m > 0 and ema3_15m < ema9_15m:
                return None
            
            # Determinar la banda Fibonacci superior activa según la zona de entrada
            upper_1 = levels.get('upper_1', basis)
            upper_2 = levels.get('upper_2', upper_1)
            upper_3 = levels.get('upper_3', upper_2)
            upper_4 = levels.get('upper_4', upper_3)
            upper_band = levels.get('upper_band_15m', basis)
            
            # Seleccionar el techo Fibonacci protector según la posición del entry_price
            if entry_price <= levels.get('lower_1', basis):
                fib_ceiling = basis
            elif entry_price <= basis:
                fib_ceiling = upper_1
            elif entry_price <= upper_1:
                fib_ceiling = upper_2
            elif entry_price <= upper_2:
                fib_ceiling = upper_3
            elif entry_price <= upper_3:
                fib_ceiling = upper_4
            else:
                fib_ceiling = upper_band
            
            # Aplicar el buffer porcentual de seguridad por encima de la banda
            sl_virtual_level = fib_ceiling * (1.0 + buffer_pct)
            
            if current_price >= sl_virtual_level:
                loss_pct = ((current_price - entry_price) / entry_price) * 100
                return {
                    "action": "close_virtual_fib_sl",
                    "close_lots": pos_lots,
                    "sl_virtual_level": format_price_precision(symbol, sl_virtual_level),
                    "fib_ceiling": format_price_precision(symbol, fib_ceiling),
                    "buffer_pct": buffer_pct * 100,
                    "rule_code": "Bb33_QSHR_FIB_VIRTUAL_SL",
                    "reason": (
                        f"SL Virtual Fibonacci SHORT: Precio ({current_price:.5f}) perforó "
                        f"Fib Ceiling ({fib_ceiling:.5f}) con buffer {buffer_pct*100:.2f}% "
                        f"(SL Virtual: {sl_virtual_level:.5f}, EMA3_15m={ema3_15m:.5f} > EMA9_15m={ema9_15m:.5f}). Pérdida: -{loss_pct:.2f}%"
                    )
                }
        
        return None
    except Exception as e:
        log_error(MODULE, f"Error evaluando SL Virtual Fibonacci {symbol}: {e}")
        return None

def evaluate_qshr_trailing_and_exit(
    position: dict,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    current_price: float,
    symbol: str,
    market_type: str = 'forex'
) -> dict | None:
    """
    Motor Dual de Salida Inteligente Multi-Mercado (Forex & Crypto / LONG & SHORT):
    1. Estrategia Activa SIPV: Salida por Clímax SIPV en 15m con soporte de Scale-Out (50% si lots >= 0.02).
    2. Niveles Extremos Fib 15m: Reversión Cuántica Híbrida en Nivel 5 o 6.
    3. ESCENARIO A (Bollinger Exhaustion Exit):
       - LONG: Si precio >= Upper BB 15m y en 5m High[-1] < High[-2] -> Cierre a mercado en la cresta.
       - SHORT: Si precio <= Lower BB 15m y en 5m Low[-1] > Low[-2] -> Cierre a mercado en el suelo.
    4. ESCENARIO B (CASCADA Fibonacci Stagnation):
       - Si no se tocó la banda extrema de Bollinger, evalúa si las últimas 3 velas de 15m muestran estancamiento:
         * LONG: High[-1] <= High[-2] <= High[-3] -> Ceñir Trailing Stop al piso Fibonacci inmediato.
         * SHORT: Low[-1] >= Low[-2] >= Low[-3] -> Ceñir Trailing Stop al techo Fibonacci inmediato.
       - Si el precio cruza el nivel protegido -> Cierre por Estancamiento Fibonacci.
    """
    if not position or df_5m is None or df_5m.empty:
        return None

    try:
        side = (position.get('side') or '').lower()
        pos_lots = abs(float(position.get('lots') or position.get('size') or position.get('shares') or 0.01))
        entry_price = float(position.get('avg_entry_price') or position.get('entry_price') or current_price)
        
        last_5m = df_5m.iloc[-1]
        prev_5m = df_5m.iloc[-2] if len(df_5m) >= 2 else last_5m
        
        high_5m_curr = float(last_5m['high'])
        high_5m_prev = float(prev_5m['high'])
        low_5m_curr = float(last_5m['low'])
        low_5m_prev = float(prev_5m['low'])
        
        levels_15m = calculate_15m_fibonacci_levels(df_15m, current_price)
        sipv_15m = calculate_sipv_indicator(df_15m)
        vel_info = calculate_5m_velocity(df_5m)
        last_15m = df_15m.iloc[-1] if df_15m is not None and not df_15m.empty else last_5m
        high_15m = float(last_15m.get('high', current_price))
        low_15m = float(last_15m.get('low', current_price))

        # ─── PASO 0 (PRIORITARIO): STOP LOSS VIRTUAL FIBONACCI ───
        # Evaluación ANTES de cualquier trailing o salida por Bollinger/SIPV.
        # Si el precio ha perforado la banda Fibonacci protectora + buffer,
        # se cierra inmediatamente. 100% controlado por eTrade, sin SL en broker.
        fib_sl_result = evaluate_fib_band_virtual_sl(position, df_15m, current_price, symbol)
        if fib_sl_result:
            log_info(MODULE, f"🛡️ [VIRTUAL FIB SL TRIGGERED] {symbol}: {fib_sl_result.get('reason')}")
            return fib_sl_result

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
                        "reason": f"QSHR Scale-Out 15m (50%): Clímax SIPV (Vol_15m={sipv_15m['vol_ratio_15m']}x). Cerrando {close_lots}L, dejando {remaining_lots}L en Trailing BB/Fib.",
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

            # 2.5. Reversión por Zona Fibonacci & Agotamiento Cinético (Fib Rejection / Triple EMA Fractura)
            pnl_curr_val = current_price - entry_price
            if pnl_curr_val > 0 and df_15m is not None and len(df_15m) >= 3:
                fib_rev = check_fib_zone_reversal_15m(
                    direction='long',
                    df_15m=df_15m,
                    pnl_current=pnl_curr_val,
                    df_5m=df_5m,
                    position=position
                )
                if fib_rev.get('is_rebote'):
                    return {
                        "action": "close_fib_zone_reversal",
                        "close_lots": pos_lots,
                        "reason": f"QSHR Fib Zone Reversal: {fib_rev['detail']}",
                        "rule_code": "Bb33_FIB_ZONE_REVERSAL_EXIT"
                    }

            # 3. ESCENARIO A: Agotamiento en Banda de Bollinger Superior
            # [ADUANA SALIDA]: Solo permite salida si el precio está en ganancia (current_price > entry_price)
            if (current_price >= levels_15m['upper_band_15m'] or high_15m >= levels_15m['upper_band_15m']) and current_price > entry_price:
                if high_5m_curr < high_5m_prev:
                    return {
                        "action": "close_bollinger_exhaustion",
                        "close_lots": pos_lots,
                        "reason": f"Bollinger Exhaustion Exit: Precio en Upper BB 15m ({levels_15m['upper_band_15m']:.5f}) y fallo de nuevo High en 5m ({high_5m_curr:.5f} < {high_5m_prev:.5f}) con beneficio",
                        "rule_code": "Bb33_BOLLINGER_EXHAUSTION_EXIT"
                    }

            # 4. ESCENARIO B: Estancamiento en Bandas de Fibonacci CASCADA (3 velas de pérdida de momentum)
            if df_15m is not None and len(df_15m) >= 3:
                h1 = float(df_15m['high'].iloc[-1])
                h2 = float(df_15m['high'].iloc[-2])
                h3 = float(df_15m['high'].iloc[-3])
                
                # Highs descendentes o planos
                if (h1 <= h2 * 1.0001) and (h2 <= h3 * 1.0001):
                    # Determinar piso Fibonacci protegido
                    basis = levels_15m['basis_15m']
                    u1 = levels_15m.get('upper_1', basis)
                    u2 = levels_15m.get('upper_2', u1)
                    u3 = levels_15m.get('upper_3', u2)
                    u4 = levels_15m.get('upper_4', u3)
                    
                    if current_price >= u4:
                        fib_floor = u3
                    elif current_price >= u3:
                        fib_floor = u2
                    elif current_price >= u2:
                        fib_floor = u1
                    elif current_price >= u1:
                        fib_floor = basis
                    else:
                        fib_floor = basis
                    
                    # Si el precio perfora el piso protegido -> Cierre de protección
                    if current_price < fib_floor and current_price > entry_price:
                        return {
                            "action": "close_cascada_fib_stagnation",
                            "close_lots": pos_lots,
                            "reason": f"CASCADA Fib Stagnation Exit: Estancamiento 3 velas 15m (Highs descendentes/planos) y quiebre de piso Fib ({current_price:.5f} < {fib_floor:.5f})",
                            "rule_code": "Bb33_CASCADA_FIB_STAGNATION_EXIT"
                        }
                    elif fib_floor > entry_price:
                        return {
                            "action": "adjust_trailing_sl",
                            "sl_price": format_price_precision(symbol, fib_floor),
                            "rule_code": "Bb33_CASCADA_FIB_TRAILING_ADJUST",
                            "reason": f"CASCADA Fib Trailing Adjust: Highs descendentes en 3 velas 15m. Ceñir SL a piso Fib ({fib_floor:.5f})"
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
                        "reason": f"QSHR Scale-Out 15m (50%): Clímax SIPV bajista (Vol_15m={sipv_15m['vol_ratio_15m']}x). Cerrando {close_lots}L, dejando {remaining_lots}L en Trailing BB/Fib.",
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

            # 2.5. Reversión por Zona Fibonacci & Agotamiento Cinético (Fib Rejection / Triple EMA Fractura)
            pnl_curr_val = entry_price - current_price
            if pnl_curr_val > 0 and df_15m is not None and len(df_15m) >= 3:
                fib_rev = check_fib_zone_reversal_15m(
                    direction='short',
                    df_15m=df_15m,
                    pnl_current=pnl_curr_val,
                    df_5m=df_5m,
                    position=position
                )
                if fib_rev.get('is_rebote'):
                    return {
                        "action": "close_fib_zone_reversal",
                        "close_lots": pos_lots,
                        "reason": f"QSHR Fib Zone Reversal: {fib_rev['detail']}",
                        "rule_code": "Bb33_FIB_ZONE_REVERSAL_EXIT"
                    }

            # 3. ESCENARIO A: Agotamiento en Banda de Bollinger Inferior
            # [ADUANA SALIDA]: Solo permite salida si el precio está en ganancia (current_price < entry_price)
            if (current_price <= levels_15m['lower_band_15m'] or low_15m <= levels_15m['lower_band_15m']) and current_price < entry_price:
                if low_5m_curr > low_5m_prev:
                    return {
                        "action": "close_bollinger_exhaustion",
                        "close_lots": pos_lots,
                        "reason": f"Bollinger Exhaustion Exit: Precio en Lower BB 15m ({levels_15m['lower_band_15m']:.5f}) y fallo de nuevo Low en 5m ({low_5m_curr:.5f} > {low_5m_prev:.5f}) con beneficio",
                        "rule_code": "Bb33_BOLLINGER_EXHAUSTION_EXIT"
                    }

            # 4. ESCENARIO B: Estancamiento en Bandas de Fibonacci CASCADA (3 velas de pérdida de momentum)
            if df_15m is not None and len(df_15m) >= 3:
                l1 = float(df_15m['low'].iloc[-1])
                l2 = float(df_15m['low'].iloc[-2])
                l3 = float(df_15m['low'].iloc[-3])
                
                # Lows ascendentes o planos
                if (l1 >= l2 * 0.9999) and (l2 >= l3 * 0.9999):
                    # Determinar techo Fibonacci protegido
                    basis = levels_15m['basis_15m']
                    d1 = levels_15m.get('lower_1', basis)
                    d2 = levels_15m.get('lower_2', d1)
                    d3 = levels_15m.get('lower_3', d2)
                    d4 = levels_15m.get('lower_4', d3)
                    
                    if current_price <= d4:
                        fib_ceiling = d3
                    elif current_price <= d3:
                        fib_ceiling = d2
                    elif current_price <= d2:
                        fib_ceiling = d1
                    elif current_price <= d1:
                        fib_ceiling = basis
                    else:
                        fib_ceiling = basis
                    
                    # Si el precio perfora el techo protegido -> Cierre de protección
                    if current_price > fib_ceiling and current_price < entry_price:
                        return {
                            "action": "close_cascada_fib_stagnation",
                            "close_lots": pos_lots,
                            "reason": f"CASCADA Fib Stagnation Exit: Estancamiento 3 velas 15m (Lows ascendentes/planos) y quiebre de techo Fib ({current_price:.5f} > {fib_ceiling:.5f})",
                            "rule_code": "Bb33_CASCADA_FIB_STAGNATION_EXIT"
                        }
                    elif fib_ceiling < entry_price:
                        return {
                            "action": "adjust_trailing_sl",
                            "sl_price": format_price_precision(symbol, fib_ceiling),
                            "rule_code": "Bb33_CASCADA_FIB_TRAILING_ADJUST",
                            "reason": f"CASCADA Fib Trailing Adjust: Lows ascendentes en 3 velas 15m. Ceñir SL a techo Fib ({fib_ceiling:.5f})"
                        }

        return None
    except Exception as e:
        log_error(MODULE, f"Error evaluando trailing/exit QSHR {symbol}: {e}")
        return None
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
            entry_px = float(active_position.get('entry_price') or active_position.get('open_price') or current_price)
            is_crypto = 'crypto' in market_type.lower() or 'USDT' in symbol
            pip_sz = 0.01 if ('JPY' in symbol or 'XAU' in symbol) else 0.0001
            pnl_pips = (current_price - entry_px) / pip_sz
            pnl_pct = (current_price - entry_px) / entry_px * 100 if entry_px > 0 else 0
            has_min_profit = (pnl_pct >= 0.25) if is_crypto else (pnl_pips >= 3.0)
            is_already_booster = active_position.get('rule_code') == 'Bb33_QSHR_BOOSTER_LONG' or active_position.get('has_booster')

            if is_expanding and is_bullish_breakout and vel_info['is_high_velocity'] and vel_info['direction'] == 'BULLISH_SURGE' and not is_already_booster and has_min_profit:
                anti_range = check_15m_anti_range_filter(df_15m, current_price, 'long', vel_info['v_5m_score'])
                if anti_range.get('passed', True) and check_triple_ema_alignment(df_5m, 'bullish'):
                    cluster_sl = calculate_cluster_stop_loss(symbol, last_5m, 'long')
                    return {
                        "action": "open_booster_long",
                        "side": "long",
                        "rule_code": "Bb33_QSHR_BOOSTER_LONG",
                        "order_type": "MARKET",
                        "sl_price": cluster_sl,
                        "velocity": vel_info['v_5m_score'],
                        "reason": f"QSHR Trend Booster LONG: Aceleración Squeeze a favor (V_5m={vel_info['v_5m_score']}, Profit={pnl_pips:.1f}pips)"
                    }

            # A1. CUT & FLIP INMEDIATO CON ASYMMETRIC SIZING (Velocity >= 2.0, EMA3<EMA9, Lower Band Break)
            ema_aligned_bearish = check_triple_ema_alignment(df_5m, 'bearish')
            at_lower_band = (current_price <= squeeze['curr_lower'])
            high_vel_bearish = (vel_info['v_5m_score'] >= 2.0) and (vel_info['direction'] == 'BEARISH_SURGE')

            if (is_bearish_breakout or at_lower_band) and high_vel_bearish and ema_aligned_bearish:
                flip_lots = calculate_asymmetric_hedge_lots(orig_lots, vel_info['v_5m_score'], capital_multiplier)
                flip_sl = calculate_cluster_stop_loss(symbol, last_5m, 'short')
                return {
                    "action": "close_and_flip_short",
                    "rule_code": "Bb33_QSHR_EARLY_EXIT",
                    "flip_side": "short",
                    "flip_rule": "Bb33_QSHR_FLIP_SHORT",
                    "flip_lots": flip_lots,
                    "sl_price": flip_sl,
                    "velocity": vel_info['v_5m_score'],
                    "reason": f"QSHR Cut & Flip SHORT: Corte LONG ({orig_lots}L) + Giro Inmediato SHORT ({flip_lots}L) por impulso bajista violento (V_5m={vel_info['v_5m_score']:.2f}, EMA3<9<20)"
                }

            # A2. Cobertura Asimétrica Acelerada SHORT (1.25x - 2.0x)
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

            # A3. Cierre de LONG Antigua por Filtro de 4 Factores
            if ema_aligned_bearish and is_expanding and at_lower_band and vel_info['is_high_velocity'] and (vel_info['direction'] == 'BEARISH_SURGE'):
                return {
                    "action": "close_original_long",
                    "rule_code": "Bb33_QSHR_EXIT",
                    "reason": f"QSHR Exit: 4 Factores validados (EMA3<9<20, Squeeze Exp, Lower Band 5m, V_5m={vel_info['v_5m_score']})"
                }

            # A4. Evaluación de Reversión y Extremos 15m
            return evaluate_qshr_trailing_and_exit(active_position, df_5m, df_15m, current_price, symbol)

        # CASO B: Posición Original es SHORT
        elif orig_side in ('short', 'sell'):
            has_hedge_long = active_position.get('has_hedge') or (active_position.get('rule_code') == 'Bb33_QSHR_HEDGE')
            is_bullish_breakout = (last_5m['close'] > last_5m['open']) and (current_price >= squeeze['curr_upper'])
            is_bearish_breakout = (last_5m['close'] < last_5m['open']) and (current_price <= squeeze['curr_lower'])

            # B0. TREND BOOSTER BAJISTA (Piramidación a Favor de SHORT)
            entry_px = float(active_position.get('entry_price') or active_position.get('open_price') or current_price)
            is_crypto = 'crypto' in market_type.lower() or 'USDT' in symbol
            pip_sz = 0.01 if ('JPY' in symbol or 'XAU' in symbol) else 0.0001
            pnl_pips = (entry_px - current_price) / pip_sz
            pnl_pct = (entry_px - current_price) / entry_px * 100 if entry_px > 0 else 0
            has_min_profit = (pnl_pct >= 0.25) if is_crypto else (pnl_pips >= 3.0)
            is_already_booster = active_position.get('rule_code') == 'Bb33_QSHR_BOOSTER_SHORT' or active_position.get('has_booster')

            if is_expanding and is_bearish_breakout and vel_info['is_high_velocity'] and vel_info['direction'] == 'BEARISH_SURGE' and not is_already_booster and has_min_profit:
                anti_range = check_15m_anti_range_filter(df_15m, current_price, 'short', vel_info['v_5m_score'])
                if anti_range.get('passed', True) and check_triple_ema_alignment(df_5m, 'bearish'):
                    cluster_sl = calculate_cluster_stop_loss(symbol, last_5m, 'short')
                    return {
                        "action": "open_booster_short",
                        "side": "short",
                        "rule_code": "Bb33_QSHR_BOOSTER_SHORT",
                        "order_type": "MARKET",
                        "sl_price": cluster_sl,
                        "velocity": vel_info['v_5m_score'],
                        "reason": f"QSHR Trend Booster SHORT: Aceleración Squeeze a favor (V_5m={vel_info['v_5m_score']}, Profit={pnl_pips:.1f}pips)"
                    }

            # B1. CUT & FLIP INMEDIATO CON ASYMMETRIC SIZING (Velocity >= 2.0, EMA3>EMA9, Upper Band Break)
            ema_aligned_bullish = check_triple_ema_alignment(df_5m, 'bullish')
            at_upper_band = (current_price >= squeeze['curr_upper'])
            high_vel_bullish = (vel_info['v_5m_score'] >= 2.0) and (vel_info['direction'] == 'BULLISH_SURGE')

            if (is_bullish_breakout or at_upper_band) and high_vel_bullish and ema_aligned_bullish:
                flip_lots = calculate_asymmetric_hedge_lots(orig_lots, vel_info['v_5m_score'], capital_multiplier)
                flip_sl = calculate_cluster_stop_loss(symbol, last_5m, 'long')
                return {
                    "action": "close_and_flip_long",
                    "rule_code": "Bb33_QSHR_EARLY_EXIT",
                    "flip_side": "long",
                    "flip_rule": "Bb33_QSHR_FLIP_LONG",
                    "flip_lots": flip_lots,
                    "sl_price": flip_sl,
                    "velocity": vel_info['v_5m_score'],
                    "reason": f"QSHR Cut & Flip LONG: Corte SHORT ({orig_lots}L) + Giro Inmediato LONG ({flip_lots}L) por impulso alcista violento (V_5m={vel_info['v_5m_score']:.2f}, EMA3>9>20)"
                }

            # B2. Cobertura Asimétrica Acelerada LONG (1.25x - 2.0x)
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

            # B3. Cierre de SHORT Antigua por Filtro de 4 Factores
            if ema_aligned_bullish and is_expanding and at_upper_band and vel_info['is_high_velocity'] and (vel_info['direction'] == 'BULLISH_SURGE'):
                return {
                    "action": "close_original_short",
                    "rule_code": "Bb33_QSHR_EXIT",
                    "reason": f"QSHR Exit: 4 Factores validados (EMA3>9>20, Squeeze Exp, Upper Band 5m, V_5m={vel_info['v_5m_score']})"
                }

            # B4. Evaluación de Reversión y Extremos 15m
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

def detect_bollinger_regime_15m(df_15m: pd.DataFrame) -> dict:
    """
    Analiza el régimen de las Bandas de Bollinger en temporalidad de 15m.
    Distingue entre:
    1. MODO EXPANSIÓN: Banda Superior con pendiente > 0, Banda Inferior con pendiente < 0,
       y ancho de banda (Bandwidth) creciente.
    2. MODO TUBO / CANAL LATERAL: Bandas paralelas o contrayéndose, EMA20 plana.
    """
    result = {
        "is_expansion": False,
        "is_tube": True,
        "upper_slope": 0.0,
        "lower_slope": 0.0,
        "bandwidth_current": 0.0,
        "bandwidth_ratio": 1.0,
        "ema20_slope": 0.0,
        "ema3": 0.0,
        "ema9": 0.0,
        "ema20": 0.0,
        "is_ema_bullish_aligned": False,
        "is_ema_bearish_aligned": False,
    }
    if df_15m is None or len(df_15m) < 4:
        return result

    try:
        upper_series = df_15m['upper_2'] if 'upper_2' in df_15m.columns else df_15m.get('bb_upper', pd.Series())
        lower_series = df_15m['lower_2'] if 'lower_2' in df_15m.columns else df_15m.get('bb_lower', pd.Series())
        basis_series = df_15m['basis'] if 'basis' in df_15m.columns else df_15m.get('sma_20', df_15m.get('ema_20', pd.Series()))

        if upper_series.empty or lower_series.empty or basis_series.empty:
            return result

        u_0 = float(upper_series.iloc[-1])
        u_1 = float(upper_series.iloc[-2])
        l_0 = float(lower_series.iloc[-1])
        l_1 = float(lower_series.iloc[-2])
        b_0 = float(basis_series.iloc[-1])
        b_1 = float(basis_series.iloc[-2])

        if b_0 <= 0 or b_1 <= 0:
            return result

        upper_slope = u_0 - u_1
        lower_slope = l_0 - l_1
        ema20_slope = b_0 - b_1

        bw_0 = (u_0 - l_0) / b_0
        bw_1 = (u_1 - l_1) / b_1
        bw_ratio = (bw_0 / bw_1) if bw_1 > 0 else 1.0

        ema3_s = df_15m.get('ema_3', df_15m.get('ema_4', df_15m.get('close', pd.Series())))
        ema9_s = df_15m.get('ema_9', pd.Series())
        ema20_s = basis_series

        ema3 = float(ema3_s.iloc[-1]) if not ema3_s.empty else b_0
        ema9 = float(ema9_s.iloc[-1]) if not ema9_s.empty else b_0
        ema20 = b_0

        ema_bullish = (ema3 > ema9) and (ema9 > ema20)
        ema_bearish = (ema3 < ema9) and (ema9 < ema20)

        # Regla de Expansión: Banda Superior abriendo hacia arriba y Banda Inferior abriendo hacia abajo
        is_expansion = (upper_slope > 0) and (lower_slope < 0) and (bw_ratio > 1.02)
        is_tube = not is_expansion

        result.update({
            "is_expansion": is_expansion,
            "is_tube": is_tube,
            "upper_slope": upper_slope,
            "lower_slope": lower_slope,
            "bandwidth_current": bw_0,
            "bandwidth_ratio": bw_ratio,
            "ema20_slope": ema20_slope,
            "ema3": ema3,
            "ema9": ema9,
            "ema20": ema20,
            "is_ema_bullish_aligned": ema_bullish,
            "is_ema_bearish_aligned": ema_bearish,
        })
        return result
    except Exception as e:
        log_warning(MODULE, f"Error calculando régimen de Bollinger 15m: {e}")
        return result


def evaluate_cluster_exit(
    symbol: str,
    active_positions: list[dict],
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    current_price: float,
    market_type: str = 'forex_futures',
    **kwargs
) -> dict | None:
    """
    Evalúa si se debe ejecutar un Take Profit en Bloque (Cluster Take Profit)
    para TODAS las posiciones activas en la misma dirección al alcanzar el clímax SIPV en 15m.
    Distingue dinámicamente entre MODO TUBO / LATERAL (TP inmediato) y MODO EXPANSIÓN (dejar correr tendencia).
    """
    if not active_positions or df_15m is None or df_15m.empty:
        return None

    try:
        sipv = calculate_sipv_indicator(df_15m)
        levels_15m = calculate_15m_fibonacci_levels(df_15m, current_price)
        bb_regime = detect_bollinger_regime_15m(df_15m)
        side = (active_positions[0].get('side') or '').lower()

        if side in ('long', 'buy'):
            # 1. En MODO EXPANSIÓN con tendencia activa: NO cerrar prematuramente
            if bb_regime['is_expansion'] and bb_regime['is_ema_bullish_aligned']:
                upper_6 = levels_15m.get('upper_6_15m', float('inf'))
                if upper_6 and current_price >= upper_6:
                    return {
                        "action": "cluster_take_profit",
                        "side": "long",
                        "position_ids": [p.get('id') for p in active_positions if p.get('id')],
                        "rule_code": "Bb33_QSHR_CLUSTER_TP",
                        "reason": f"QSHR Cluster TP 15m: Clímax Parabólico Extremo en Upper_6 ({len(active_positions)} posiciones cerradas)"
                    }
                log_info(MODULE, f"🚀 [QSHR CLUSTER TP SKIP] [{symbol} LONG]: Modo Expansión 15m activo con EMA3>EMA9>EMA20. Dejando correr tendencia.")
                return None

            # 2. En MODO TUBO / CANAL LATERAL: Take Profit al tocar la banda superior
            if (current_price >= levels_15m['upper_5_15m'] or current_price >= levels_15m['upper_band_15m']):
                return {
                    "action": "cluster_take_profit",
                    "side": "long",
                    "position_ids": [p.get('id') for p in active_positions if p.get('id')],
                    "rule_code": "Bb33_QSHR_CLUSTER_TP",
                    "reason": f"QSHR Cluster TP 15m: Take Profit en Banda Superior (Modo Tubo / Rango Lateral) ({len(active_positions)} posiciones cerradas)"
                }

        elif side in ('short', 'sell'):
            # 1. En MODO EXPANSIÓN con tendencia activa: NO cerrar prematuramente
            if bb_regime['is_expansion'] and bb_regime['is_ema_bearish_aligned']:
                lower_6 = levels_15m.get('lower_6_15m', 0.0)
                if lower_6 and current_price <= lower_6:
                    return {
                        "action": "cluster_take_profit",
                        "side": "short",
                        "position_ids": [p.get('id') for p in active_positions if p.get('id')],
                        "rule_code": "Bb33_QSHR_CLUSTER_TP",
                        "reason": f"QSHR Cluster TP 15m: Clímax Parabólico Extremo en Lower_6 ({len(active_positions)} posiciones cerradas)"
                    }
                log_info(MODULE, f"🚀 [QSHR CLUSTER TP SKIP] [{symbol} SHORT]: Modo Expansión 15m activo con EMA3<EMA9<EMA20. Dejando correr tendencia.")
                return None

            # 2. En MODO TUBO / CANAL LATERAL: Take Profit al tocar la banda inferior
            if (current_price <= levels_15m['lower_5_15m'] or current_price <= levels_15m['lower_band_15m']):
                return {
                    "action": "cluster_take_profit",
                    "side": "short",
                    "position_ids": [p.get('id') for p in active_positions if p.get('id')],
                    "rule_code": "Bb33_QSHR_CLUSTER_TP",
                    "reason": f"QSHR Cluster TP 15m: Take Profit en Banda Inferior (Modo Tubo / Rango Lateral) ({len(active_positions)} posiciones cerradas)"
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


