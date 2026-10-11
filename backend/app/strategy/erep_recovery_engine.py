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
    halcon_scores: dict = None,
    market_type: str = 'forex_futures',
    df_1h: pd.DataFrame = None,
    df_4h: pd.DataFrame = None,
    df_1d: pd.DataFrame = None,
) -> dict | None:
    """
    Evalua si se cumplen las condiciones para disparar la entrada de rescate P2:
    1. Zona Extrema REBOTE: Upper_5/6_15m o Upper_Band o EMA9/EMA20 de 1h/4h (para SHORT),
       o Lower_5/6_15m o Lower_Band o EMA9/EMA20 de 1h/4h (para LONG).
    2. Agotamiento SIPV 15m: Climax de volumen institucional y mecha de rechazo.
    3. Estado RADAR: Desaceleracion o giro (pullback o real_reversal).
    4. Seguridad ADUANAS: Velocidad V_5m < 2.5 (Sin Squeeze activo en contra).
    Soporta Crypto y Forex, LONG y SHORT.
    """
    if not position or df_5m is None or df_15m is None:
        return None

    try:
        p1_price = float(position.get('entry_price') or 0.0)
        p1_size = float(position.get('lots') or position.get('size') or 0.01)
        side = (position.get('side') or '').lower()
        symbol = position.get('symbol', 'GBPUSD')
        is_crypto = 'crypto' in market_type.lower() or 'USDT' in symbol.upper() or 'USDC' in symbol.upper()
        
        if position.get('erep_p2_price') and float(position.get('erep_p2_price')) > 0:
            return None

        if is_crypto:
            drawdown_pct = ((p1_price - current_price) / p1_price * 100) if side in ('long', 'buy') else ((current_price - p1_price) / p1_price * 100)
            if drawdown_pct < 0.40:
                return None
            dist_pips = drawdown_pct * 10.0
            pip_factor = current_price * 0.0001
        else:
            is_gold = 'XAU' in symbol.upper() or 'GOLD' in symbol.upper()
            is_jpy = 'JPY' in symbol.upper()
            pip_factor = 0.01 if (is_jpy or is_gold) else 0.0001
            if side in ('short', 'sell'):
                dist_diff = current_price - p1_price
            else:
                dist_diff = p1_price - current_price

            dist_pips = dist_diff / pip_factor
            min_pips = 500.0 if is_gold else 15.0  # $5.00 USD en Oro o 15 pips en Forex Majors
            if dist_pips < min_pips:
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

        # ── 1. PROTECCIÓN DE QUIEBRE ESTRUCTURAL CATASTRÓFICO FOREX ──
        atr_15m = float(levels_15m.get('atr_15m') or (15.0 * pip_factor))
        catastrophic_buffer = 1.2 * atr_15m
        l6 = float(levels_15m.get('lower_6_15m') or 0.0)
        u6 = float(levels_15m.get('upper_6_15m') or 0.0)

        if side in ('long', 'buy') and l6 > 0 and current_price <= (l6 - catastrophic_buffer):
            return {
                'action': 'erep_structural_breakdown',
                'side': 'long',
                'reason': f"🚨 QUIEBRE ESTRUCTURAL CATASTRÓFICO FOREX: Precio {current_price:.5f} perforó suelo LOWER_6 ({l6:.5f} - 1.2*ATR). Corte de emergencia para evitar pérdidas masivas."
            }
        elif side in ('short', 'sell') and u6 > 0 and current_price >= (u6 + catastrophic_buffer):
            return {
                'action': 'erep_structural_breakdown',
                'side': 'short',
                'reason': f"🚨 QUIEBRE ESTRUCTURAL CATASTRÓFICO FOREX: Precio {current_price:.5f} superó techo UPPER_6 ({u6:.5f} + 1.2*ATR). Corte de emergencia para evitar pérdidas masivas."
            }

        # ── 2. DETECCIÓN DE SOPORTES Y RESISTENCIAS EN EMA9 / EMA20 Y BOLLINGER DE 1H / 4H ──
        ema9_1h = 0.0
        ema20_1h = 0.0
        ema9_4h = 0.0
        ema20_4h = 0.0
        bb_upper_1h = 0.0
        bb_lower_1h = 0.0

        if df_1h is not None and len(df_1h) >= 9:
            c1h = df_1h['close'] if 'close' in df_1h.columns else df_1h.get('c', pd.Series())
            ema9_1h = float(c1h.ewm(span=9, adjust=False).mean().iloc[-1]) if len(c1h) >= 9 else 0.0
            ema20_1h = float(c1h.ewm(span=20, adjust=False).mean().iloc[-1]) if len(c1h) >= 20 else 0.0
            if len(c1h) >= 20:
                m1h = float(c1h.rolling(20).mean().iloc[-1])
                s1h = float(c1h.rolling(20).std().iloc[-1])
                bb_upper_1h = m1h + 2.0 * s1h
                bb_lower_1h = m1h - 2.0 * s1h
        elif snap:
            ema9_1h = float(snap.get('ema9_1h') or snap.get('ema_9_1h') or 0.0)
            ema20_1h = float(snap.get('ema20_1h') or snap.get('ema_20_1h') or 0.0)
            bb_upper_1h = float(snap.get('upper_1h') or snap.get('bb_upper_1h') or 0.0)
            bb_lower_1h = float(snap.get('lower_1h') or snap.get('bb_lower_1h') or 0.0)

        if df_4h is not None and len(df_4h) >= 9:
            c4h = df_4h['close'] if 'close' in df_4h.columns else df_4h.get('c', pd.Series())
            ema9_4h = float(c4h.ewm(span=9, adjust=False).mean().iloc[-1]) if len(c4h) >= 9 else 0.0
            ema20_4h = float(c4h.ewm(span=20, adjust=False).mean().iloc[-1]) if len(c4h) >= 20 else 0.0
        elif snap:
            ema9_4h = float(snap.get('ema9_4h') or snap.get('ema_9_4h') or 0.0)
            ema20_4h = float(snap.get('ema20_4h') or snap.get('ema_20_4h') or 0.0)

        ema_tolerance = 0.0020 if is_crypto else 0.0006

        # ── VERIFICAR TENDENCIA MACRO 1D ──
        macro_1d_aligned = False
        if df_1d is not None and len(df_1d) >= 2:
            c1d = df_1d['close'] if 'close' in df_1d.columns else df_1d.get('c', pd.Series())
            if len(c1d) >= 2:
                e3_1d = float(c1d.ewm(span=3, adjust=False).mean().iloc[-1])
                e3_prev = float(c1d.ewm(span=3, adjust=False).mean().iloc[-2])
                e9_1d = float(c1d.ewm(span=9, adjust=False).mean().iloc[-1])
                if side in ('long', 'buy') and (e3_1d >= e9_1d or e3_1d >= e3_prev):
                    macro_1d_aligned = True
                elif side in ('short', 'sell') and (e3_1d <= e9_1d or e3_1d <= e3_prev):
                    macro_1d_aligned = True
        elif snap:
            trend_1d = str(snap.get('trend_1d') or snap.get('regime_1d') or '').lower()
            if side in ('long', 'buy') and 'bull' in trend_1d:
                macro_1d_aligned = True
            elif side in ('short', 'sell') and 'bear' in trend_1d:
                macro_1d_aligned = True

        # ── 3. CASCADA DE GRADOS FIBONACCI (LOWER_3 a LOWER_6 / UPPER_3 a UPPER_6) ──
        snap_levels = {
            'basis': levels_15m.get('basis_15m', 0.0),
            'lower_3': levels_15m.get('lower_3', 0.0),
            'lower_4': levels_15m.get('lower_4', 0.0),
            'lower_5': levels_15m.get('lower_5_15m', 0.0),
            'lower_6': levels_15m.get('lower_6_15m', 0.0),
            'upper_3': levels_15m.get('upper_3', 0.0),
            'upper_4': levels_15m.get('upper_4', 0.0),
            'upper_5': levels_15m.get('upper_5_15m', 0.0),
            'upper_6': levels_15m.get('upper_6_15m', 0.0),
        }
        from app.strategy.erep_manager import get_fibonacci_erep_target
        fib_ladder = get_fibonacci_erep_target(p1_price, current_price, side, snap_levels)

        if side in ('short', 'sell'):
            target_band_reached = fib_ladder.get('reached', False)
            tested_ema_resistance = False
            ema_res_name = ""
            for ema_val, name in [(ema9_4h, "EMA9_4h"), (ema20_4h, "EMA20_4h"), (ema9_1h, "EMA9_1h"), (ema20_1h, "EMA20_1h")]:
                if ema_val > 0 and abs(current_price - ema_val) / ema_val <= ema_tolerance:
                    tested_ema_resistance = True
                    ema_res_name = name
                    break

            tested_1h_bollinger = (bb_upper_1h > 0 and current_price >= (bb_upper_1h - buffer_val))

            at_upper_extreme = (
                target_band_reached
                or (current_price >= (levels_15m['upper_5_15m'] - buffer_val))
                or (current_price >= (levels_15m['upper_band_15m'] - buffer_val))
                or tested_ema_resistance
                or tested_1h_bollinger
            )
            radar_pullback = (ema3_curr <= ema3_prev) or (sipv['upper_wick_ratio'] >= 0.20) or tested_1h_bollinger or macro_1d_aligned
            
            if at_upper_extreme and (sipv['is_bullish_climax'] or radar_pullback):
                q2_size = round(p1_size * 1.5, 4) if is_crypto else calculate_erep_p2_sizing(p1_size, dist_pips, halcon_score=0.0)
                p3_avg = calculate_erep_weighted_breakeven(p1_price, p1_size, current_price, q2_size, symbol)
                if tested_1h_bollinger:
                    band_desc = 'UPPER_BB_1H'
                elif target_band_reached:
                    band_desc = fib_ladder.get('target_band', 'upper_5').upper()
                elif tested_ema_resistance:
                    band_desc = ema_res_name.upper()
                else:
                    band_desc = 'UPPER_5'
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
                    'target_band': band_desc,
                    'reason': f"EREP v2.0 Rescate SHORT en 1H: P2 {q2_size} en {band_desc} ({current_price:.5f}). P3 Breakeven = {p3_avg:.5f} (Dist={dist_pips:.1f}p)"
                }

        elif side in ('long', 'buy'):
            target_band_reached = fib_ladder.get('reached', False)
            tested_ema_support = False
            ema_supp_name = ""
            for ema_val, name in [(ema9_4h, "EMA9_4h"), (ema20_4h, "EMA20_4h"), (ema9_1h, "EMA9_1h"), (ema20_1h, "EMA20_1h")]:
                if ema_val > 0 and abs(current_price - ema_val) / ema_val <= ema_tolerance:
                    tested_ema_support = True
                    ema_supp_name = name
                    break

            tested_1h_bollinger = (bb_lower_1h > 0 and current_price <= (bb_lower_1h + buffer_val))

            at_lower_extreme = (
                target_band_reached
                or (current_price <= (levels_15m['lower_5_15m'] + buffer_val))
                or (current_price <= (levels_15m['lower_band_15m'] + buffer_val))
                or tested_ema_support
                or tested_1h_bollinger
            )
            radar_pullback = (ema3_curr >= ema3_prev) or (sipv['lower_wick_ratio'] >= 0.20) or tested_1h_bollinger or macro_1d_aligned

            if at_lower_extreme and (sipv['is_bearish_climax'] or radar_pullback):
                q2_size = round(p1_size * 1.5, 4) if is_crypto else calculate_erep_p2_sizing(p1_size, dist_pips, halcon_score=0.0)
                p3_avg = calculate_erep_weighted_breakeven(p1_price, p1_size, current_price, q2_size, symbol)
                if tested_1h_bollinger:
                    band_desc = 'LOWER_BB_1H'
                elif target_band_reached:
                    band_desc = fib_ladder.get('target_band', 'lower_5').upper()
                elif tested_ema_support:
                    band_desc = ema_supp_name.upper()
                else:
                    band_desc = 'LOWER_5'
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
                    'target_band': band_desc,
                    'reason': f"EREP v2.0 Rescate LONG en 1H: P2 {q2_size} en {band_desc} ({current_price:.5f}). P3 Breakeven = {p3_avg:.5f} (Dist={dist_pips:.1f}p)"
                }

        return None
    except Exception as e:
        log_error(MODULE, f"Error evaluando EREP Entry Trigger: {e}")
        return None

def evaluate_erep_exit_trigger(
    position_p1: dict,
    current_price: float,
    symbol: str = 'GBPUSD',
    allow_partial_derisk: bool = False,
    df_15m: pd.DataFrame = None,
    df_1h: pd.DataFrame = None,
    df_5m: pd.DataFrame = None,
) -> dict | None:
    """
    Evalua si el precio actual ha alcanzado o superado el precio promedio P3.
    NUEVO PARADIGMA:
    - Si al llegar a P3 la EMA3 tiene inercia a favor (slope > 0 para LONG o slope < 0 para SHORT):
      PROHIBIDO CERRAR EN P3. Blindar Stop Loss a P3 (+buffer) y mantener RUNNER hacia la Banda de Bollinger.
    - Si el precio alcanza la Banda Superior/Inferior de Bollinger: Cierre masivo con máxima ganancia.
    - Si la EMA3 gira en contra por encima de P3: Cierre por agotamiento de momentum asegurando ganancia.
    - Si la EMA3 es plana o desfavorable al tocar P3: Cierre defensivo estándar en Breakeven.
    """
    if not position_p1:
        return None

    try:
        p3_avg = float(position_p1.get('erep_p3_avg') or position_p1.get('avg_price') or position_p1.get('avg_entry_price') or 0.0)
        is_erep_active = bool(position_p1.get('erep_active')) or (position_p1.get('erep_phase', 0) >= 2) or (position_p1.get('erep_purchases_count', 0) > 0) or (bool(position_p1.get('erep_p2_price')) and float(position_p1.get('erep_p2_price') or 0) > 0)
        side = (position_p1.get('side') or '').lower()

        if p3_avg <= 0.0 or not is_erep_active:
            return None

        is_crypto = 'USDT' in symbol.upper() or 'USDC' in symbol.upper() or 'crypto' in str(position_p1.get('market_type', '')).lower()
        buffer_val = (p3_avg * 0.001) if is_crypto else (0.0002 if 'JPY' in symbol or 'XAU' in symbol else 0.0002)

        # Determinar DataFrame de análisis para EMA3 y Bandas de Bollinger
        target_df = df_15m if df_15m is not None and len(df_15m) >= 3 else (df_1h if df_1h is not None and len(df_1h) >= 3 else (df_5m if df_5m is not None and len(df_5m) >= 3 else None))

        upper_bb = float(position_p1.get('upper_bb') or 0.0)
        lower_bb = float(position_p1.get('lower_bb') or 0.0)

        ema3_slope = 0.0
        has_df = False

        if target_df is not None and len(target_df) >= 3:
            col_c = target_df['close'] if 'close' in target_df.columns else target_df.get('c', pd.Series())
            if len(col_c) >= 3:
                ema3_s = col_c.ewm(span=3, adjust=False).mean()
                ema3_slope = float(ema3_s.iloc[-1] - ema3_s.iloc[-2])
                has_df = True

            if upper_bb <= 0:
                if 'upper_band' in target_df.columns:
                    upper_bb = float(target_df['upper_band'].iloc[-1])
                elif 'bb_upper' in target_df.columns:
                    upper_bb = float(target_df['bb_upper'].iloc[-1])
                elif len(col_c) >= 20:
                    upper_bb = float(col_c.rolling(20).mean().iloc[-1] + 2 * col_c.rolling(20).std().iloc[-1])

            if lower_bb <= 0:
                if 'lower_band' in target_df.columns:
                    lower_bb = float(target_df['lower_band'].iloc[-1])
                elif 'bb_lower' in target_df.columns:
                    lower_bb = float(target_df['bb_lower'].iloc[-1])
                elif len(col_c) >= 20:
                    lower_bb = float(col_c.rolling(20).mean().iloc[-1] - 2 * col_c.rolling(20).std().iloc[-1])

        is_runner_active = bool(position_p1.get('erep_runner_active'))

        if side in ('short', 'sell'):
            # 1. OBJETIVO MAYOR: Precio alcanza Banda Inferior de Bollinger
            if lower_bb > 0 and lower_bb < p3_avg and current_price <= (lower_bb * 1.001):
                return {
                    'action': 'close_erep_cluster',
                    'side': 'short',
                    'p3_avg': p3_avg,
                    'current_price': current_price,
                    'rule_code': 'Bb33_EREP_CLUSTER_EXIT_LOWER_BB',
                    'reason': f"🎯 TP EREP CLÍMAX BANDA INFERIOR: Precio {current_price:.5f} alcanzó Lower_BB ({lower_bb:.5f}). Cierre del 100% con beneficio asegurado."
                }

            # 2. EVALUACIÓN AL CRUCE DE P3 (Break-Even)
            if current_price <= p3_avg:
                # Si EMA3 tiene pendiente negativa (fuerza bajista intacta), NO cerrar en P3 -> RUNNER
                if has_df and ema3_slope < 0:
                    new_sl = round(p3_avg - buffer_val, 6)
                    target_tp = lower_bb if lower_bb > 0 else round(p3_avg * 0.985, 6)
                    return {
                        'action': 'hold_erep_runner_to_lower_bb',
                        'side': 'short',
                        'p3_avg': p3_avg,
                        'current_price': current_price,
                        'new_sl': new_sl,
                        'target_tp': target_tp,
                        'rule_code': 'Bb33_EREP_RUNNER_LOWER_BB',
                        'reason': f"🏃 EREP v2.0 Breakeven P3 Alcanzado ({current_price:.5f} <= {p3_avg:.5f}) con EMA3 bajista (slope={ema3_slope:.6f}). SL blindado a {new_sl:.5f} y Runner activo hacia Banda Inferior ({target_tp:.5f})."
                    }

                # 3. SALIDA POR AGOTAMIENTO SI RUNNER YA ESTABA ACTIVO
                if is_runner_active and has_df and ema3_slope > 0:
                    return {
                        'action': 'close_erep_cluster',
                        'side': 'short',
                        'p3_avg': p3_avg,
                        'current_price': current_price,
                        'rule_code': 'Bb33_EREP_CLUSTER_EXIT_EXHAUSTION',
                        'reason': f"⚠️ EREP v2.0 Salida por Agotamiento: EMA3 giró al alza ({ema3_slope:.6f}) por debajo de P3 ({current_price:.5f} < {p3_avg:.5f}). Cerrando en beneficio."
                    }

                if allow_partial_derisk and not position_p1.get('erep_be_partial'):
                    return {
                        'action': 'erep_cluster_derisk_partial',
                        'close_pct': 0.50,
                        'side': 'short',
                        'p3_avg': p3_avg,
                        'current_price': current_price,
                        'rule_code': 'Bb33_EREP_CLUSTER_DERISK_50',
                        'reason': f"EREP v2.0 Breakeven Alcanzado: Precio {current_price:.5f} <= P3 {p3_avg:.5f}. Desarmando 50% en Breakeven ($0 riesgo) y runner a Basis."
                    }

                return {
                    'action': 'close_erep_cluster',
                    'side': 'short',
                    'p3_avg': p3_avg,
                    'current_price': current_price,
                    'rule_code': 'Bb33_EREP_CLUSTER_EXIT',
                    'reason': f"EREP v2.0 Breakeven Alcanzado: Precio {current_price:.5f} <= P3 {p3_avg:.5f}. Cierre masivo de rescate ejecutado."
                }

        elif side in ('long', 'buy'):
            # 1. OBJETIVO MAYOR: Precio alcanza Banda Superior de Bollinger
            if upper_bb > p3_avg and current_price >= (upper_bb * 0.999):
                return {
                    'action': 'close_erep_cluster',
                    'side': 'long',
                    'p3_avg': p3_avg,
                    'current_price': current_price,
                    'rule_code': 'Bb33_EREP_CLUSTER_EXIT_UPPER_BB',
                    'reason': f"🎯 TP EREP CLÍMAX BANDA SUPERIOR: Precio {current_price:.5f} alcanzó Upper_BB ({upper_bb:.5f}). Cierre del 100% con beneficio asegurado."
                }

            # 2. EVALUACIÓN AL CRUCE DE P3 (Break-Even)
            if current_price >= p3_avg:
                # Si EMA3 tiene pendiente positiva (fuerza alcista intacta), NO cerrar en P3 -> RUNNER
                if has_df and ema3_slope > 0:
                    new_sl = round(p3_avg + buffer_val, 6)
                    target_tp = upper_bb if upper_bb > 0 else round(p3_avg * 1.015, 6)
                    return {
                        'action': 'hold_erep_runner_to_upper_bb',
                        'side': 'long',
                        'p3_avg': p3_avg,
                        'current_price': current_price,
                        'new_sl': new_sl,
                        'target_tp': target_tp,
                        'rule_code': 'Bb33_EREP_RUNNER_UPPER_BB',
                        'reason': f"🏃 EREP v2.0 Breakeven P3 Alcanzado ({current_price:.5f} >= {p3_avg:.5f}) con EMA3 alcista (slope={ema3_slope:.6f}). SL blindado a {new_sl:.5f} y Runner activo hacia Banda Superior ({target_tp:.5f})."
                    }

                # 3. SALIDA POR AGOTAMIENTO SI RUNNER YA ESTABA ACTIVO
                if is_runner_active and has_df and ema3_slope < 0:
                    return {
                        'action': 'close_erep_cluster',
                        'side': 'long',
                        'p3_avg': p3_avg,
                        'current_price': current_price,
                        'rule_code': 'Bb33_EREP_CLUSTER_EXIT_EXHAUSTION',
                        'reason': f"⚠️ EREP v2.0 Salida por Agotamiento: EMA3 giró a la baja ({ema3_slope:.6f}) por encima de P3 ({current_price:.5f} > {p3_avg:.5f}). Cerrando en beneficio."
                    }

                if allow_partial_derisk and not position_p1.get('erep_be_partial'):
                    return {
                        'action': 'erep_cluster_derisk_partial',
                        'close_pct': 0.50,
                        'side': 'long',
                        'p3_avg': p3_avg,
                        'current_price': current_price,
                        'rule_code': 'Bb33_EREP_CLUSTER_DERISK_50',
                        'reason': f"EREP v2.0 Breakeven Alcanzado: Precio {current_price:.5f} >= P3 {p3_avg:.5f}. Desarmando 50% en Breakeven ($0 riesgo) y runner a Basis."
                    }

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


def evaluate_climax_ema_transition(
    position: dict,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    current_price: float,
    symbol: str,
    market_type: str = 'crypto_futures'
) -> dict | None:
    """
    Motor de Escalera de Transición de EMAs y Toma de Ganancias para posiciones CLIMAX / EREP.
    Soporta LONG y SHORT, Crypto y Forex.
    
    Fases del Ciclo de Vida:
    - Fase 1: Holding / Absorción (Protegido por Hard Stop estructural).
    - Fase 2: Micro-Giro 5m (EMA3_5m cruza a favor de la posición) -> SL a Breakeven de P3 / Entrada.
    - Fase 3: TP1 Parcial en Basis 15m (50% de la posición al alcanzar la media).
    - Fase 4: Confirmación Macro 15m (EMA3 > EMA9 > EMA20 para LONG o EMA3 < EMA9 < EMA20 para SHORT).
    - Fase 5: TP2 Runner en Upper_2 / Lower_2 o agotamiento de tendencia (EMA3 x EMA9 reverso).
    """
    if not position or df_15m is None or len(df_15m) < 15 or df_5m is None or len(df_5m) < 10:
        return None

    try:
        rule = (position.get('rule_code') or '').lower()
        is_climax = any(x in rule for x in ('climax', 'lower6', 'upper6', 'reversal'))
        is_erep = bool(position.get('erep_active')) or (position.get('erep_phase', 0) > 0)
        
        if not is_climax and not is_erep:
            return None

        side = (position.get('side') or '').lower()
        is_long = side in ('long', 'buy')
        entry_price = float(position.get('erep_p3_avg') or position.get('avg_entry_price') or position.get('entry_price') or current_price)
        pos_id = position.get('id')

        # Niveles de Fibonacci y Basis 15m
        levels_15m = calculate_15m_fibonacci_levels(df_15m, current_price)
        basis_15m = float(levels_15m.get('basis_15m') or current_price)

        # EMAs en 5m
        c5 = df_5m['close'] if 'close' in df_5m.columns else df_5m.get('c', pd.Series())
        ema3_5m = float(c5.ewm(span=3, adjust=False).mean().iloc[-1]) if len(c5) >= 5 else 0.0
        ema9_5m = float(c5.ewm(span=9, adjust=False).mean().iloc[-1]) if len(c5) >= 9 else 0.0
        last_5m = df_5m.iloc[-1]
        c5_close = float(last_5m.get('close', 0))
        c5_open = float(last_5m.get('open', 0))

        # EMAs en 15m
        c15 = df_15m['close'] if 'close' in df_15m.columns else df_15m.get('c', pd.Series())
        ema3_15m = float(c15.ewm(span=3, adjust=False).mean().iloc[-1]) if len(c15) >= 10 else 0.0
        ema9_15m = float(c15.ewm(span=9, adjust=False).mean().iloc[-1]) if len(c15) >= 10 else 0.0
        ema20_15m = float(c15.ewm(span=20, adjust=False).mean().iloc[-1]) if len(c15) >= 20 else 0.0

        # ─── HITO 1: TP1 PARCIAL EN BASIS 15M (50% de la Posición) ───
        # Al tocar la media móvil central de Bollinger (Basis), tomar 50% de ganancia asegurada.
        if not position.get('partial_closed'):
            if is_long and current_price >= basis_15m and current_price > entry_price:
                return {
                    'action': 'climax_tp_partial_basis',
                    'rule_code': 'climax_basis_tp1',
                    'close_pct': 0.50,
                    'target_price': basis_15m,
                    'reason': f"Clímax Reversal LONG: Alcanzó Basis 15m (${basis_15m:,.2f}) en ganancia. Ejecutando TP1 Parcial 50%."
                }
            elif (not is_long) and current_price <= basis_15m and current_price < entry_price:
                return {
                    'action': 'climax_tp_partial_basis',
                    'rule_code': 'climax_basis_tp1',
                    'close_pct': 0.50,
                    'target_price': basis_15m,
                    'reason': f"Clímax Reversal SHORT: Alcanzó Basis 15m (${basis_15m:,.2f}) en ganancia. Ejecutando TP1 Parcial 50%."
                }

        # ─── HITO 2: ROTACIÓN MACRO 15M (EMA3 > EMA9 > EMA20 o EMA3 < EMA9 < EMA20) ───
        # Si la tendencia macro rotó completamente, la reversión triunfó y ahora es un trade de tendencia.
        if is_long:
            is_macro_trend = (ema3_15m > ema9_15m > ema20_15m) and (ema20_15m > 0)
            if is_macro_trend:
                # Salida por Runner en Upper_2 o Upper_3
                u2 = levels_15m.get('upper_2', float('inf'))
                if current_price >= u2:
                    return {
                        'action': 'climax_tp_full',
                        'rule_code': 'climax_tp_upper2',
                        'target_price': u2,
                        'reason': f"Clímax Reversal LONG: Objetivo Upper_2 alcanzado (${current_price:,.2f}). Cerrando posición restante con beneficio."
                    }
                # Si la rotación estaba confirmada pero EMA3 cruza a la baja de EMA9 con ganancia, cerrar runner
                if position.get('trend_confirmed') and ema3_15m < ema9_15m and current_price > entry_price:
                    return {
                        'action': 'climax_tp_full',
                        'rule_code': 'climax_exhaustion_exit',
                        'reason': f"Clímax Reversal LONG: Agotamiento de tendencia post-rotación (EMA3_15m < EMA9_15m). Cerrando en beneficio."
                    }
                # Confirmar tendencia y elevar SL a BE / trailing
                curr_sl = float(position.get('sl_price') or 0)
                if curr_sl < entry_price:
                    return {
                        'action': 'confirm_trend',
                        'trend': 'bullish',
                        'new_sl': entry_price,
                        'reason': f"Rotación Macro 15m LONG Confirmada (EMA3 > EMA9 > EMA20). Elevando SL a Breakeven (${entry_price:,.2f})."
                    }
        else:
            is_macro_trend = (ema3_15m < ema9_15m < ema20_15m) and (ema20_15m > 0)
            if is_macro_trend:
                l2 = levels_15m.get('lower_2', 0.0)
                if l2 > 0 and current_price <= l2:
                    return {
                        'action': 'climax_tp_full',
                        'rule_code': 'climax_tp_lower2',
                        'target_price': l2,
                        'reason': f"Clímax Reversal SHORT: Objetivo Lower_2 alcanzado (${current_price:,.2f}). Cerrando posición restante con beneficio."
                    }
                if position.get('trend_confirmed') and ema3_15m > ema9_15m and current_price < entry_price:
                    return {
                        'action': 'climax_tp_full',
                        'rule_code': 'climax_exhaustion_exit',
                        'reason': f"Clímax Reversal SHORT: Agotamiento de tendencia post-rotación (EMA3_15m > EMA9_15m). Cerrando en beneficio."
                    }
                curr_sl = float(position.get('sl_price') or float('inf'))
                if curr_sl > entry_price:
                    return {
                        'action': 'confirm_trend',
                        'trend': 'bearish',
                        'new_sl': entry_price,
                        'reason': f"Rotación Macro 15m SHORT Confirmada (EMA3 < EMA9 < EMA20). Elevando SL a Breakeven (${entry_price:,.2f})."
                    }

        # ─── HITO 3: MICRO-GIRO 5M (Giro inicial hacia Breakeven con Buffer Inteligente) ───
        # Cuando en 5m la micro-media gira a favor de la operación con ganancia mínima (+0.25% Crypto / 5 pips Forex),
        # mover SL a Breakeven para blindar capital sin ahogar la posición por mero spread de entrada.
        if not position.get('be_activated'):
            is_crypto = 'crypto' in (market_type or '').lower() or 'USDT' in symbol.upper() or 'USDC' in symbol.upper()
            be_buffer_pct = 0.0025 if is_crypto else 0.0005  # 0.25% en Crypto, ~5 pips en Forex
            
            if is_long:
                profit_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0.0
                if ema3_5m > ema9_5m and c5_close > c5_open and profit_pct >= be_buffer_pct:
                    return {
                        'action': 'adjust_sl_be',
                        'new_sl': entry_price,
                        'reason': f"Micro-Giro 5m LONG Confirmado (EMA3_5m={ema3_5m:.2f} > EMA9_5m={ema9_5m:.2f}) con margen +{profit_pct*100:.2f}%. Blindando en Breakeven (${entry_price:,.2f})."
                    }
            elif (not is_long):
                profit_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0.0
                if ema3_5m < ema9_5m and c5_close < c5_open and profit_pct >= be_buffer_pct:
                    return {
                        'action': 'adjust_sl_be',
                        'new_sl': entry_price,
                        'reason': f"Micro-Giro 5m SHORT Confirmado (EMA3_5m={ema3_5m:.2f} < EMA9_5m={ema9_5m:.2f}) con margen +{profit_pct*100:.2f}%. Blindando en Breakeven (${entry_price:,.2f})."
                    }

        return None
    except Exception as trans_err:
        log_error(MODULE, f"Error evaluando Climax EMA Transition para {symbol}: {trans_err}")
        return None


def evaluate_erep_dca_step(
    position: dict,
    candle_15m: pd.Series | dict,
    max_purchases: int = 3,
    market_type: str = 'forex_futures'
) -> dict | None:
    """
    Evalúa si se debe ejecutar una compra/venta EREP escalonada al CIERRE de una vela de 15 minutos.
    Regla de Usuario: Si el precio sigue cayendo (LONG) o subiendo (SHORT) y al cierre de la vela 15m
    el precio es más desfavorable que el precio promedio de la posición, ejecutar recompra hasta
    el límite establecido (max_purchases, default 3).
    """
    if not position or candle_15m is None:
        return None

    try:
        # 1. Verificar si ya alcanzó el límite máximo de compras EREP
        purchases_count = int(position.get('erep_purchases_count', 0))
        if purchases_count >= max_purchases:
            return None

        side = (position.get('side') or '').lower()
        is_long = side in ('long', 'buy')
        avg_price = float(position.get('avg_price') or position.get('avg_entry_price') or position.get('entry_price') or 0.0)
        if avg_price <= 0:
            return None

        close_15m = float(candle_15m.get('close', 0.0))
        if close_15m <= 0:
            return None

        p1_qty = float(position.get('p1_qty') or position.get('lots') or position.get('size') or 0.01)
        curr_qty = float(position.get('current_qty') or p1_qty)
        symbol = position.get('symbol', '')

        # 2. Condición de precio y distancia mínima real para no promediar por micro-ruidos
        is_crypto = ('crypto' in market_type.lower() or 'USDT' in symbol.upper() or 'USDC' in symbol.upper())
        if is_crypto:
            dist_pct = ((avg_price - close_15m) / avg_price * 100) if is_long else ((close_15m - avg_price) / avg_price * 100)
            if dist_pct < 0.35:
                return None
        else:
            pip_f = 0.01 if ('JPY' in symbol or 'XAU' in symbol) else 0.0001
            dist_pips = ((avg_price - close_15m) / pip_f) if is_long else ((close_15m - avg_price) / pip_f)
            min_pips = 300.0 if 'XAU' in symbol else (20.0 if 'JPY' in symbol else 12.0)
            if dist_pips < min_pips:
                return None

        if is_long and close_15m < avg_price:
            # Compra escalonada LONG (1.0x el tamaño de P1)
            new_qty = p1_qty
            new_avg = ((avg_price * curr_qty) + (close_15m * new_qty)) / (curr_qty + new_qty)
            new_count = purchases_count + 1
            return {
                'action': 'execute_erep_dca_step',
                'side': 'long',
                'rule_code': f"Bb33_EREP_DCA_STEP_{new_count}",
                'order_type': 'MARKET',
                'fill_price': close_15m,
                'add_qty': new_qty,
                'new_avg_price': new_avg,
                'new_total_qty': curr_qty + new_qty,
                'step_number': new_count,
                'reason': f"EREP DCA Step #{new_count} LONG: Cierre 15m (${close_15m:.5f}) < AvgPrice (${avg_price:.5f}). Nuevo Avg = ${new_avg:.5f}"
            }
        elif (not is_long) and close_15m > avg_price:
            # Venta escalonada SHORT (1.0x el tamaño de P1)
            new_qty = p1_qty
            new_avg = ((avg_price * curr_qty) + (close_15m * new_qty)) / (curr_qty + new_qty)
            new_count = purchases_count + 1
            return {
                'action': 'execute_erep_dca_step',
                'side': 'short',
                'rule_code': f"Bb33_EREP_DCA_STEP_{new_count}",
                'order_type': 'MARKET',
                'fill_price': close_15m,
                'add_qty': new_qty,
                'new_avg_price': new_avg,
                'new_total_qty': curr_qty + new_qty,
                'step_number': new_count,
                'reason': f"EREP DCA Step #{new_count} SHORT: Cierre 15m (${close_15m:.5f}) > AvgPrice (${avg_price:.5f}). Nuevo Avg = ${new_avg:.5f}"
            }

        return None
    except Exception as e:
        log_error(MODULE, f"Error evaluando EREP DCA Step para {position}: {e}")
        return None


