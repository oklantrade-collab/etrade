"""
Level Evaluator for CASCADA — Rebote vs Continuation Check.
eTrade v5.0 — Spec Section 3.3, 3.4 & 3.5
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional


def check_sipv_reversal_15m(
    direction: str,
    df_15m: Optional[pd.DataFrame],
    pnl_current: float,
    position: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Detector SIPV de Reversión Confirmada en 15m:
    Para SHORT:
      1. Toque previo de Banda Inferior de Bollinger (o Lowest Price <= Lower BB).
      2. 2 velas consecutivas de 15m con mínimos ascendentes (Higher Lows: Low[-1] >= Low[-2] y Low[0] >= Low[-1]).
      3. Cierre actual de 15m cruzando por encima de MA3 o EMA3.
      4. PnL positivo o en break-even.
    Para LONG:
      1. Toque previo de Banda Superior de Bollinger (o Highest Price >= Upper BB).
      2. 2 velas consecutivas de 15m con máximos descendentes (Lower Highs: High[-1] <= High[-2] y High[0] <= High[-1]).
      3. Cierre actual de 15m cruzando por debajo de MA3 o EMA3.
      4. PnL positivo o en break-even.
    """
    if df_15m is None or len(df_15m) < 3:
        return {'is_rebote': False, 'reason': 'INSUFFICIENT_DATA', 'detail': 'df_15m tiene menos de 3 velas'}

    if pnl_current <= 0:
        return {'is_rebote': False, 'reason': 'PNL_NOT_POSITIVE', 'detail': f'PnL (${pnl_current:.2f}) no es positivo'}

    is_short = direction.lower() in ('short', 'sell')
    df = df_15m.copy()
    if 'ema3' not in df.columns:
        df['ema3'] = df['close'].ewm(span=3, adjust=False).mean()
    if 'sma3' not in df.columns:
        df['sma3'] = df['close'].rolling(3).mean()
    if 'lower_2' not in df.columns and 'bb_lower' not in df.columns:
        sma20 = df['close'].rolling(20).mean()
        std20 = df['close'].rolling(20).std()
        df['lower_2'] = sma20 - (std20 * 2)
        df['upper_2'] = sma20 + (std20 * 2)

    col_lower = 'lower_2' if 'lower_2' in df.columns else ('bb_lower' if 'bb_lower' in df.columns else None)
    col_upper = 'upper_2' if 'upper_2' in df.columns else ('bb_upper' if 'bb_upper' in df.columns else None)

    r0 = df.iloc[-1]
    r1 = df.iloc[-2]
    r2 = df.iloc[-3]

    c0 = float(r0['close'])
    l0 = float(r0['low'])
    h0 = float(r0['high'])
    ma3_0 = float(r0.get('sma3') or r0.get('ema3') or c0)
    ema3_0 = float(r0.get('ema3') or c0)

    l1 = float(r1['low'])
    h1 = float(r1['high'])
    l2 = float(r2['low'])
    h2 = float(r2['high'])

    if is_short:
        # 1. Contacto con banda inferior en alguna de las últimas 3 velas
        lower_bb_touched = False
        if col_lower:
            for r in (r2, r1, r0):
                b_val = float(r.get(col_lower, 0))
                if b_val > 0 and float(r['low']) <= b_val * 1.0005:
                    lower_bb_touched = True
                    break
        if not lower_bb_touched and position:
            band_str = str(position.get('highest_band_reached', ''))
            if 'bb_touched' in band_str or 'lower' in band_str:
                lower_bb_touched = True

        # 2. Higher Lows en las últimas 2 velas
        has_higher_lows = (l0 >= l1 * 0.9999) and (l1 >= l2 * 0.9999)

        # 3. Cruce alcista de MA3 / EMA3
        crossed_ma3_up = (c0 >= ma3_0 * 0.9999) or (c0 >= ema3_0 * 0.9999)

        if lower_bb_touched and has_higher_lows and crossed_ma3_up:
            return {
                'is_rebote': True,
                'reason': 'SIPV_15M_REVERSAL_CONFIRMED',
                'detail': f'SIPV Reversión SHORT 15m: Toque Lower BB + 2 Higher Lows ({l0:.5f} >= {l1:.5f} >= {l2:.5f}) + Cruce MA3 ({c0:.5f} > {ma3_0:.5f}) con PnL +${pnl_current:.2f}'
            }
    else:
        # 1. Contacto con banda superior en alguna de las últimas 3 velas
        upper_bb_touched = False
        if col_upper:
            for r in (r2, r1, r0):
                b_val = float(r.get(col_upper, 0))
                if b_val > 0 and float(r['high']) >= b_val * 0.9995:
                    upper_bb_touched = True
                    break
        if not upper_bb_touched and position:
            band_str = str(position.get('highest_band_reached', ''))
            if 'bb_touched' in band_str or 'upper' in band_str:
                upper_bb_touched = True

        # 2. Lower Highs en las últimas 2 velas
        has_lower_highs = (h0 <= h1 * 1.0001) and (h1 <= h2 * 1.0001)

        # 3. Cruce bajista de MA3 / EMA3
        crossed_ma3_down = (c0 <= ma3_0 * 1.0001) or (c0 <= ema3_0 * 1.0001)

        if upper_bb_touched and has_lower_highs and crossed_ma3_down:
            return {
                'is_rebote': True,
                'reason': 'SIPV_15M_REVERSAL_CONFIRMED',
                'detail': f'SIPV Reversión LONG 15m: Toque Upper BB + 2 Lower Highs ({h0:.5f} <= {h1:.5f} <= {h2:.5f}) + Cruce MA3 ({c0:.5f} < {ma3_0:.5f}) con PnL +${pnl_current:.2f}'
            }

    return {'is_rebote': False, 'reason': 'NO_SIPV_REVERSAL', 'detail': 'Patrón SIPV 15m no completado'}


def calculate_fib_exhaustion_velocity(df_5m: Optional[pd.DataFrame], direction: str = 'long') -> Dict[str, Any]:
    """
    Calcula la velocidad de avance por minuto de la vela actual de 5m
    y la compara con el promedio de las últimas 9 velas de 5m (45 minutos / ciclo EMA9).
    """
    if df_5m is None or len(df_5m) < 9:
        return {'is_exhausted': False, 'k_ratio': 1.0, 'v_curr': 0.0, 'v_avg9': 0.0}

    try:
        last = df_5m.iloc[-1]
        c_curr = float(last['close'])
        o_curr = float(last['open'])
        
        # Crecimiento por minuto en vela actual (5 min)
        v_curr = (c_curr - o_curr) / 5.0
        
        # Velocidad media absoluta de las últimas 9 velas de 5m
        closes_9 = df_5m['close'].iloc[-9:]
        opens_9 = df_5m['open'].iloc[-9:]
        total_delta_9 = (closes_9 - opens_9).abs().sum()
        v_avg9 = float(total_delta_9) / 45.0
        
        if v_avg9 <= 0:
            v_avg9 = abs(v_curr) if abs(v_curr) > 0 else 0.00001

        is_long = direction.lower() in ('long', 'buy')
        if is_long:
            k_ratio = v_curr / v_avg9
            is_exhausted = (k_ratio < 0.25) or (v_curr <= 0)
        else:
            k_ratio = (-v_curr) / v_avg9
            is_exhausted = (k_ratio < 0.25) or (v_curr >= 0)

        return {
            'is_exhausted': bool(is_exhausted),
            'k_ratio': round(float(k_ratio), 2),
            'v_curr': round(float(v_curr), 6),
            'v_avg9': round(float(v_avg9), 6)
        }
    except Exception:
        return {'is_exhausted': False, 'k_ratio': 1.0, 'v_curr': 0.0, 'v_avg9': 0.0}


def check_fib_zone_reversal_15m(
    direction: str,
    df_15m: Optional[pd.DataFrame],
    pnl_current: float,
    df_5m: Optional[pd.DataFrame] = None,
    position: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Detector de Agotamiento y Reversión en Bandas de Fibonacci (Fib Zone Traversal & Reversal):
    Condiciones:
      1. PnL > 0 (posición en ganancia).
      2. Previa o activa alineación Triple EMA:
         - Para LONG: EMA3 > EMA9 > EMA20
         - Para SHORT: EMA3 < EMA9 < EMA20
      3. Contacto / Testeo de Banda Fibonacci >= Upper_2 (0.382 Fib) o <= Lower_2.
      4. Falla de continuación / Agotamiento cinético / Fractura de EMA3:
         - Para LONG: Close < Upper_Band_testeada O Close < EMA3 O High[-1] <= High[-2] con K_ratio < 0.25
         - Para SHORT: Close > Lower_Band_testeada O Close > EMA3 O Low[-1] >= Low[-2] con K_ratio < 0.25
    """
    if df_15m is None or len(df_15m) < 3:
        return {'is_rebote': False, 'reason': 'INSUFFICIENT_DATA', 'detail': 'df_15m tiene menos de 3 velas'}

    if pnl_current <= 0:
        return {'is_rebote': False, 'reason': 'PNL_NOT_POSITIVE', 'detail': f'PnL (${pnl_current:.2f}) no es positivo'}

    is_long = direction.lower() in ('long', 'buy')
    df = df_15m.copy()

    # Cálculo de EMAs
    if 'ema3' not in df.columns:
        df['ema3'] = df['close'].ewm(span=3, adjust=False).mean()
    if 'ema9' not in df.columns:
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    if 'ema20' not in df.columns:
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()

    # Bandas Fibonacci
    c = df['close']
    sma20 = df['close'].rolling(20, min_periods=1).mean()
    std20 = df['close'].rolling(20, min_periods=1).std()
    
    basis = float(sma20.iloc[-1])
    std = float(std20.iloc[-1])
    if std == 0:
        std = float(c.iloc[-1]) * 0.001

    u1 = basis + (0.236 * 3.0 * std)
    u2 = basis + (0.382 * 3.0 * std)
    u3 = basis + (0.500 * 3.0 * std)
    u4 = basis + (0.618 * 3.0 * std)

    d1 = basis - (0.236 * 3.0 * std)
    d2 = basis - (0.382 * 3.0 * std)
    d3 = basis - (0.500 * 3.0 * std)
    d4 = basis - (0.618 * 3.0 * std)

    r0 = df.iloc[-1]
    r1 = df.iloc[-2]
    
    c0 = float(r0['close'])
    h0 = float(r0['high'])
    l0 = float(r0['low'])
    ema3_0 = float(r0['ema3'])
    ema9_0 = float(r0['ema9'])
    ema20_0 = float(r0['ema20'])

    h1 = float(r1['high'])
    l1 = float(r1['low'])
    ema3_1 = float(r1['ema3'])
    ema9_1 = float(r1['ema9'])
    ema20_1 = float(r1['ema20'])

    vel_5m = calculate_fib_exhaustion_velocity(df_5m, direction)

    if is_long:
        ema_aligned_bull = (ema3_1 >= ema9_1 >= ema20_1 * 0.9999) or (ema3_0 >= ema9_0 >= ema20_0 * 0.9999)
        max_high = max(h0, h1)
        tested_band = None
        band_name = None
        if max_high >= u4 * 0.9998:
            tested_band = u4
            band_name = 'Upper_4 (0.618)'
        elif max_high >= u3 * 0.9998:
            tested_band = u3
            band_name = 'Upper_3 (0.500)'
        elif max_high >= u2 * 0.9998:
            tested_band = u2
            band_name = 'Upper_2 (0.382)'

        if ema_aligned_bull and tested_band:
            broken_ema3 = (c0 <= ema3_0 * 1.0001)
            rejected_band = (c0 < tested_band)
            failing_highs = (h0 <= h1 * 1.0001)

            if (rejected_band and broken_ema3) or (failing_highs and broken_ema3 and vel_5m['is_exhausted']):
                return {
                    'is_rebote': True,
                    'reason': 'FIB_ZONE_REVERSAL_CONFIRMED',
                    'detail': f'Reversión Fib LONG 15m: Testeo de {band_name} (${tested_band:.5f}, High={max_high:.5f}) con rechazo de cierre (${c0:.5f} < {ema3_0:.5f} EMA3, K_ratio={vel_5m["k_ratio"]}) y PnL +${pnl_current:.2f}',
                    'tested_band': band_name,
                    'tested_band_price': tested_band,
                    'k_ratio': vel_5m['k_ratio']
                }
    else:
        # SHORT
        ema_aligned_bear = (ema3_1 <= ema9_1 <= ema20_1 * 1.0001) or (ema3_0 <= ema9_0 <= ema20_0 * 1.0001)
        min_low = min(l0, l1)
        tested_band = None
        band_name = None
        if min_low <= d4 * 1.0002:
            tested_band = d4
            band_name = 'Lower_4 (0.618)'
        elif min_low <= d3 * 1.0002:
            tested_band = d3
            band_name = 'Lower_3 (0.500)'
        elif min_low <= d2 * 1.0002:
            tested_band = d2
            band_name = 'Lower_2 (0.382)'

        if ema_aligned_bear and tested_band:
            broken_ema3 = (c0 >= ema3_0 * 0.9999)
            rejected_band = (c0 > tested_band)
            failing_lows = (l0 >= l1 * 0.9999)

            if (rejected_band and broken_ema3) or (failing_lows and broken_ema3 and vel_5m['is_exhausted']):
                return {
                    'is_rebote': True,
                    'reason': 'FIB_ZONE_REVERSAL_CONFIRMED',
                    'detail': f'Reversión Fib SHORT 15m: Testeo de {band_name} (${tested_band:.5f}, Low={min_low:.5f}) con rechazo de cierre (${c0:.5f} > {ema3_0:.5f} EMA3, K_ratio={vel_5m["k_ratio"]}) y PnL +${pnl_current:.2f}',
                    'tested_band': band_name,
                    'tested_band_price': tested_band,
                    'k_ratio': vel_5m['k_ratio']
                }

    return {'is_rebote': False, 'reason': 'NO_FIB_REVERSAL', 'detail': 'Patrón Fib Reversal no completado'}


def check_rebote(
    direction: str,
    radar_snapshot: Dict[str, Any],
    pnl_current: float,
    current_level: int,
    df_15m: Optional[pd.DataFrame] = None,
    position: Optional[Dict[str, Any]] = None,
    df_5m: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Evaluates Section 3.3 (a): Chequeo de Rebote & Reversión SIPV y Fibonacci.
    """
    is_short = direction.lower() in ('short', 'sell')
    slope_ema3 = radar_snapshot.get('pendiente_EMA3', 'sin_datos')
    slope_ema20 = radar_snapshot.get('pendiente_EMA20', 'sin_datos')

    pnl_positive = pnl_current > 0

    if not pnl_positive:
        return {
            'is_rebote': False,
            'reason': 'PNL_NOT_POSITIVE',
            'detail': f"PnL (${pnl_current:.2f}) is not positive; rebote exit not applicable"
        }

    # 0. Evaluación prioritaria de Reversión por Bandas Fibonacci y SIPV 15m
    if df_15m is not None and len(df_15m) >= 3:
        fib_eval = check_fib_zone_reversal_15m(direction, df_15m, pnl_current, df_5m, position)
        if fib_eval['is_rebote']:
            return fib_eval

        sipv_eval = check_sipv_reversal_15m(direction, df_15m, pnl_current, position)
        if sipv_eval['is_rebote']:
            return sipv_eval

    # For SHORT position (seeking falling prices):
    if is_short:
        # Rebound is fast EMA3 turning ASCENDING
        ema3_turned_up = (slope_ema3 == 'ascending')
        ema20_holds_down = (slope_ema20 == 'descending')

        if ema3_turned_up:
            if ema20_holds_down:
                # Section 3.5: Pullback in intact bearish trend -> NOT real reversal
                return {
                    'is_rebote': False,
                    'reason': 'PULLBACK_IN_INTACT_TREND',
                    'detail': 'EMA3 ascending but EMA20 descending: Short-term pullback in intact bearish trend (not real rebound)'
                }
            else:
                # Real rebound: EMA3 ascending and EMA20 lateral/ascending
                return {
                    'is_rebote': True,
                    'reason': 'REAL_REVERSAL_CONFIRMED',
                    'detail': f"Valid rebote detected at N{current_level}: EMA3 ascending and EMA20 not descending (PnL: ${pnl_current:.2f})"
                }

    # For LONG position (seeking rising prices):
    else:
        # Rebound/reversal is fast EMA3 turning DESCENDING
        ema3_turned_down = (slope_ema3 == 'descending')
        ema20_holds_up = (slope_ema20 == 'ascending')

        if ema3_turned_down:
            if ema20_holds_up:
                # Pullback in intact bullish trend -> NOT real reversal
                return {
                    'is_rebote': False,
                    'reason': 'PULLBACK_IN_INTACT_TREND',
                    'detail': 'EMA3 descending but EMA20 ascending: Short-term pullback in intact bullish trend (not real rebound)'
                }
            else:
                # Real reversal
                return {
                    'is_rebote': True,
                    'reason': 'REAL_REVERSAL_CONFIRMED',
                    'detail': f"Valid rebote detected at N{current_level}: EMA3 descending and EMA20 not ascending (PnL: ${pnl_current:.2f})"
                }

    return {
        'is_rebote': False,
        'reason': 'TREND_ALIGNED',
        'detail': 'Fast EMA aligned with position direction'
    }


def check_continuacion(
    direction: str,
    current_level: int,
    df_15m: Optional[pd.DataFrame],
    df_higher_tf: Optional[pd.DataFrame],  # 1h dataframe (used for N2-N5)
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Evaluates Section 3.3 (b) & 3.4: Chequeo de Continuación (Señales de Apoyo).
    
    Support signals:
    (i) Upper Bollinger band (15m) flattening or descending for SHORT (lower band rising for LONG).
    (ii) Highs/Lows descending/ascending over last 3 closed candles (15m in N1, 1h in N2-N5).
    
    Returns:
        {
            'confirmed': bool,
            'bb_signal': bool,
            'structure_signal': bool,
            'detail': str
        }
    """
    is_short = direction.lower() in ('short', 'sell')
    lookback = params.get('hh_lookback_candles', 3)

    # 1. Bollinger Band Support Signal (i) on 15m
    bb_signal = False
    if df_15m is not None and len(df_15m) >= 4:
        try:
            # Check upper band for SHORT, lower band for LONG
            band_col = 'upper_6' if is_short else 'lower_6'
            if band_col not in df_15m.columns:
                band_col = 'upper_1' if is_short else 'lower_1'

            if band_col in df_15m.columns:
                curr_band = float(df_15m[band_col].iloc[-2])
                prev_band = float(df_15m[band_col].iloc[-4])  # 2 candles back
                
                if is_short:
                    # Upper band flattening or descending
                    bb_signal = curr_band <= prev_band * 1.0005
                else:
                    # Lower band flattening or ascending
                    bb_signal = curr_band >= prev_band * 0.9995
        except Exception:
            bb_signal = False

    # 2. Price Structure Support Signal (ii)
    # 15m for N1, higher TF (1h) for N2-N5
    struct_df = df_15m if current_level <= 1 else (df_higher_tf if df_higher_tf is not None else df_15m)
    struct_signal = False

    if struct_df is not None and len(struct_df) >= lookback + 2:
        try:
            closed_candles = struct_df.iloc[-lookback - 1 : -1]
            if is_short:
                # Consecutive descending HIGHs
                highs = closed_candles['high'].values
                struct_signal = all(highs[i] >= highs[i + 1] for i in range(len(highs) - 1))
            else:
                # Consecutive ascending LOWs
                lows = closed_candles['low'].values
                struct_signal = all(lows[i] <= lows[i + 1] for i in range(len(lows) - 1))
        except Exception:
            struct_signal = False

    # Continuation is confirmed if at least one strong support signal holds
    confirmed = bb_signal or struct_signal

    tf_label = "15m" if current_level <= 1 else "1h"
    return {
        'confirmed': confirmed,
        'bb_signal': bb_signal,
        'structure_signal': struct_signal,
        'detail': (
            f"Continuation confirmed (BB signal: {bb_signal}, {tf_label} structure: {struct_signal})"
            if confirmed else
            f"Continuation not confirmed (BB signal: {bb_signal}, {tf_label} structure: {struct_signal})"
        )
    }
