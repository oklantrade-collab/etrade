"""
eTrader v5.0 -- EREP v2.0 Quantum Recovery Engine
=================================================
Modulo de Rescate Cuantico por Escalamiento Asimetrico (EREP v2.0).
Integrado con:
* REBOTE Cuantico (Niveles Fibonacci 15m y SIPV Climax)
* RADAR (Matriz de Pendientes EMA3 x EMA20)
* ADUANAS Gateway (Control de Riesgo y Bloqueo en Squeeze)
* HALCON CENTINELA (Modulacion Asimetrica 1x - 3x)
* CASCADA (Salida en Breakeven P3 y Trailing hacia Basis)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from app.core.logger import log_info, log_warning, log_error
from app.strategy.quantum_squeeze_hedge import (
    calculate_15m_fibonacci_levels,
    calculate_sipv_indicator,
    calculate_5m_velocity,
    detect_bollinger_squeeze_expansion,
    format_price_precision
)

MODULE = 'EREP_V2'

def calculate_erep_p2_sizing(
    p1_size: float,
    distance_pips: float,
    halcon_score: float = 0.0,
    market_type: str = 'forex_futures'
) -> float:
    """
    Calcula el tamano optimo de la orden de rescate P2 (Q2).
    - Drawdown moderado (< 50 pips): Q2 = 1.0x - 1.5x Q1
    - Drawdown profundo (>= 50 pips): Q2 = 2.0x - 3.0x Q1
    Garantiza el respeto de la granularidad minima (0.01 lots en Forex).
    """
    base_lots = max(0.01, abs(float(p1_size or 0.01)))
    dist = abs(float(distance_pips or 0.0))

    if dist >= 70.0:
        multiplier = 3.0
    elif dist >= 45.0:
        multiplier = 2.0
    elif dist >= 25.0:
        multiplier = 1.5
    else:
        multiplier = 1.0

    if halcon_score >= 0.5:
        multiplier = min(3.0, multiplier + 0.5)

    q2_calc = round(base_lots * multiplier, 2)
    if base_lots == 0.01:
        if multiplier >= 2.5:
            q2_calc = 0.03
        elif multiplier >= 1.5:
            q2_calc = 0.02
        else:
            q2_calc = 0.01

    return max(0.01, round(q2_calc, 2))

def calculate_erep_weighted_breakeven(
    p1_price: float,
    q1_size: float,
    p2_price: float,
    q2_size: float,
    symbol: str = 'GBPUSD'
) -> float:
    """
    Calcula el precio promedio ponderado exacto P3:
    P3 = (P1 * Q1 + P2 * Q2) / (Q1 + Q2)
    """
    p1 = float(p1_price)
    q1 = max(0.0001, float(q1_size))
    p2 = float(p2_price)
    q2 = max(0.0001, float(q2_size))

    total_size = q1 + q2
    p3_weighted = ((p1 * q1) + (p2 * q2)) / total_size
    return format_price_precision(symbol, p3_weighted)

def evaluate_erep_entry_trigger(
    position: dict,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    current_price: float,
    snap: dict = None,
    halcon_scores: dict = None
) -> dict | None:
    """
    Evalua si se cumplen las 4 condiciones para disparar la entrada de rescate P2:
    1. Zona Extrema REBOTE: Upper_5/6_15m o Upper_Band (para SHORT) o Lower_5/6_15m (para LONG).
    2. Agotamiento SIPV 15m: Climax de volumen institucional y mecha de rechazo.
    3. Estado RADAR: Desaceleracion o giro (pullback o real_reversal).
    4. Seguridad ADUANAS: Velocidad V_5m < 2.5 (Sin Squeeze activo en contra).
    """
    if not position or df_5m is None or df_15m is None:
        return None

    try:
        p1_price = float(position.get('entry_price') or 0.0)
        p1_size = float(position.get('lots') or position.get('size') or 0.01)
        side = (position.get('side') or '').lower()
        symbol = position.get('symbol', 'GBPUSD')
        is_jpy = 'JPY' in symbol.upper()
        pip_factor = 0.01 if is_jpy else 0.0001

        if position.get('erep_p2_price') and float(position.get('erep_p2_price')) > 0:
            return None

        if side in ('short', 'sell'):
            dist_pips = (current_price - p1_price) / pip_factor
        else:
            dist_pips = (p1_price - current_price) / pip_factor

        if dist_pips < 25.0:
            return None

        vel = calculate_5m_velocity(df_5m)
        if vel['is_high_velocity'] and vel['v_5m_score'] >= 2.5:
            return None

        levels_15m = calculate_15m_fibonacci_levels(df_15m, current_price)
        sipv = calculate_sipv_indicator(df_15m)

        last_5m = df_5m.iloc[-1]
        ema3_curr = float(last_5m.get('ma3') or df_5m['close'].ewm(span=3).mean().iloc[-1])
        ema3_prev = float(df_5m['close'].ewm(span=3).mean().iloc[-2]) if len(df_5m) >= 2 else ema3_curr

        buffer_val = 2.0 * pip_factor

        if side in ('short', 'sell'):
            at_upper_extreme = (current_price >= (levels_15m['upper_5_15m'] - buffer_val)) or (current_price >= (levels_15m['upper_band_15m'] - buffer_val))
            radar_pullback = (ema3_curr <= ema3_prev) or (sipv['upper_wick_ratio'] >= 0.30)
            
            if at_upper_extreme and (sipv['is_bullish_climax'] or radar_pullback):
                q2_size = calculate_erep_p2_sizing(p1_size, dist_pips, halcon_score=0.0)
                p3_avg = calculate_erep_weighted_breakeven(p1_price, p1_size, current_price, q2_size, symbol)
                return {
                    'action': 'execute_erep_p2',
                    'side': 'short',
                    'rule_code': 'Bb33_EREP_RECOVERY_P2',
                    'order_type': 'MARKET',
                    'p1_price': p1_price,
                    'p1_size': p1_size,
                    'p2_price': current_price,
                    'p2_size': q2_size,
                    'p3_avg': p3_avg,
                    'distance_pips': round(dist_pips, 1),
                    'reason': f"EREP v2.0 Rescate SHORT: P2 {q2_size}L en Upper_5 ({current_price:.5f}). P3 Breakeven = {p3_avg:.5f} (Dist={dist_pips:.1f}p)"
                }

        elif side in ('long', 'buy'):
            at_lower_extreme = (current_price <= (levels_15m['lower_5_15m'] + buffer_val)) or (current_price <= (levels_15m['lower_band_15m'] + buffer_val))
            radar_pullback = (ema3_curr >= ema3_prev) or (sipv['lower_wick_ratio'] >= 0.30)

            if at_lower_extreme and (sipv['is_bearish_climax'] or radar_pullback):
                q2_size = calculate_erep_p2_sizing(p1_size, dist_pips, halcon_score=0.0)
                p3_avg = calculate_erep_weighted_breakeven(p1_price, p1_size, current_price, q2_size, symbol)
                return {
                    'action': 'execute_erep_p2',
                    'side': 'long',
                    'rule_code': 'Bb33_EREP_RECOVERY_P2',
                    'order_type': 'MARKET',
                    'p1_price': p1_price,
                    'p1_size': p1_size,
                    'p2_price': current_price,
                    'p2_size': q2_size,
                    'p3_avg': p3_avg,
                    'distance_pips': round(dist_pips, 1),
                    'reason': f"EREP v2.0 Rescate LONG: P2 {q2_size}L en Lower_5 ({current_price:.5f}). P3 Breakeven = {p3_avg:.5f} (Dist={dist_pips:.1f}p)"
                }

        return None
    except Exception as e:
        log_error(MODULE, f"Error evaluando EREP Entry Trigger: {e}")
        return None

def evaluate_erep_exit_trigger(
    position_p1: dict,
    current_price: float,
    symbol: str = 'GBPUSD'
) -> dict | None:
    """
    Evalua si el precio actual ha alcanzado o superado el precio promedio P3
    para ejecutar el Cierre Masivo de Rescate en Breakeven / Profit.
    """
    if not position_p1:
        return None

    try:
        p3_avg = float(position_p1.get('erep_p3_avg') or 0.0)
        p2_price = float(position_p1.get('erep_p2_price') or 0.0)
        side = (position_p1.get('side') or '').lower()

        if p3_avg <= 0.0 or p2_price <= 0.0:
            return None

        if side in ('short', 'sell'):
            if current_price <= p3_avg:
                return {
                    'action': 'close_erep_cluster',
                    'side': 'short',
                    'p3_avg': p3_avg,
                    'current_price': current_price,
                    'rule_code': 'Bb33_EREP_CLUSTER_EXIT',
                    'reason': f"EREP v2.0 Breakeven Alcanzado: Precio {current_price:.5f} <= P3 {p3_avg:.5f}. Cierre masivo de rescate ejecutado."
                }

        elif side in ('long', 'buy'):
            if current_price >= p3_avg:
                return {
                    'action': 'close_erep_cluster',
                    'side': 'long',
                    'p3_avg': p3_avg,
                    'current_price': current_price,
                    'rule_code': 'Bb33_EREP_CLUSTER_EXIT',
                    'reason': f"EREP v2.0 Breakeven Alcanzado: Precio {current_price:.5f} >= P3 {p3_avg:.5f}. Cierre masivo de rescate ejecutado."
                }

        return None
    except Exception as e:
        log_error(MODULE, f"Error evaluando EREP Exit Trigger: {e}")
        return None
