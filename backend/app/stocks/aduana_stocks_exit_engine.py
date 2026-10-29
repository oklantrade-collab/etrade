"""
eTrade v6.0 — ADUANA STOCKS EXIT ENGINE
=======================================
Motor Integral de Salidas y Tomas de Beneficio para Acciones (Stocks Spot).
Sincronización Multi-Timeframe (5m, 15m, 1H, 4H, 1D).

Pilares Operativos:
1. El Combustible Estructural (15m): Volumen relativo (RVOL), pendiente de volumen
   y dirección de vela en 15m. Si el combustible es ALTO, protege el trade y
   guarda espacio evitando cierres prematuros por ruido en 5m.
2. Sub-Bandas de Fibonacci en 3 Tercios (15m): Cada tramo entre bandas se divide
   en Sub-Banda 1 (inicio), Sub-Banda 2 (expansión) y Sub-Banda 3 (agotamiento).
3. Micro-Gatillos de Precisión en 5m: Detección de giro EMA3 < EMA9, aplanamiento
   de Banda Bollinger Superior (slope <= 0) y cierre bajo EMA3.
4. Bollinger Macro (1H, 4H, 1D): Tomas escalonadas (TP1 Parcial 50% en 1H,
   TP Mayoritario 75% o Total 100% en 4H / 1D).
5. Trailing Stop Acelerado en UPPER_5 / UPPER_6: Toma de 50% al clímax y trailing
   vela a vela en 5m anclado a Low[t-1] y EMA3 para proteger el 85-95% de la ganancia.
6. Erradicación Total de Bloqueos: Cero filtros de $1.00 USD, cero sabotaje de Stop Loss a 0.
"""

import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.core.logger import log_info, log_warning, log_error
from app.strategy.panic_recovery_gate import calculate_fibonacci_bands

MODULE = "ADUANA_STOCKS_EXIT"


def _safe_col(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Retorna la serie de la columna en minúscula o Capitalizada de forma segura."""
    if col_name in df.columns:
        return df[col_name].astype(float)
    cap = col_name.capitalize()
    if cap in df.columns:
        return df[cap].astype(float)
    upper = col_name.upper()
    if upper in df.columns:
        return df[upper].astype(float)
    return pd.Series(dtype=float)


def calculate_fibonacci_sub_bands(current_price: float, bands: dict, side: str = 'long') -> dict:
    """
    Divide los intervalos de bandas de Fibonacci (1..6) en 3 sub-bandas iguales y 3 Zonas Estructurales:
      Zona 1 (Basis a Upper_1 / Lower_1): Gestación / Arranque. Prohibido salir por agotamiento.
      Zona 2 (Upper_1 a Upper_3 / Lower_1 a Lower_3): Desarrollo. Salida al agotar con ganancia >= 1.5%.
      Zona 3 (Upper_3 a Upper_6+): Clímax y Sobre-extensión institucional.
    
    Sub-Banda 1 (0% a 33.3%): Arranque del tramo
    Sub-Banda 2 (33.3% a 66.6%): Expansión media
    Sub-Banda 3 (66.6% a 100%): Agotamiento relativo del tramo
    """
    is_long = side.lower() in ('long', 'buy')
    basis = float(bands.get('basis', current_price))
    atr = float(bands.get('atr', current_price * 0.01))

    if is_long:
        levels = [
            ('basis', basis),
            ('upper_1', float(bands.get('upper_1', basis * 1.005))),
            ('upper_2', float(bands.get('upper_2', basis * 1.010))),
            ('upper_3', float(bands.get('upper_3', basis * 1.015))),
            ('upper_4', float(bands.get('upper_4', basis * 1.020))),
            ('upper_5', float(bands.get('upper_5', basis * 1.030))),
            ('upper_6', float(bands.get('upper_6', basis * 1.040))),
            ('upper_climax', float(bands.get('upper_6', basis * 1.040)) + (atr * 1.5))
        ]
        
        # Encontrar en qué intervalo se ubica el precio
        for i in range(len(levels) - 1):
            name_low, p_low = levels[i]
            name_high, p_high = levels[i + 1]
            if p_low <= current_price <= p_high or i == len(levels) - 2 and current_price >= p_high:
                span = max(1e-6, p_high - p_low)
                progress = max(0.0, min(1.0, (current_price - p_low) / span))
                if progress < 0.3333:
                    sub_idx = 1
                elif progress < 0.6666:
                    sub_idx = 2
                else:
                    sub_idx = 3

                # Mapeo de Zona:
                # Zona 1: basis a upper_1 (Gestación)
                # Zona 2: upper_1 a upper_3 (Desarrollo)
                # Zona 3: upper_3 en adelante (Clímax)
                if name_low == 'basis':
                    zone = 1
                elif name_low in ('upper_1', 'upper_2'):
                    zone = 2
                else:
                    zone = 3

                # En Zona 1 (Gestación) NUNCA se declara agotamiento
                in_exhaustion = (sub_idx == 3) and (zone > 1)
                in_extreme = name_high in ('upper_5', 'upper_6', 'upper_climax') or (name_high == 'upper_4' and sub_idx == 3)

                return {
                    'interval': f"{name_low}_to_{name_high}",
                    'major_target': name_high,
                    'target_price': p_high,
                    'zone': zone,
                    'sub_band': sub_idx,
                    'progress_pct': round(progress * 100.0, 1),
                    'in_exhaustion_zone': in_exhaustion,
                    'in_extreme_zone': in_extreme,
                    'is_upper6': current_price >= float(bands.get('upper_6', 0))
                }

        # Por debajo de basis
        return {
            'interval': 'below_basis',
            'major_target': 'basis',
            'target_price': basis,
            'zone': 1,
            'sub_band': 1,
            'progress_pct': 0.0,
            'in_exhaustion_zone': False,
            'in_extreme_zone': False,
            'is_upper6': False
        }

    else:
        # SHORT (hacia abajo)
        levels = [
            ('basis', basis),
            ('lower_1', float(bands.get('lower_1', basis * 0.995))),
            ('lower_2', float(bands.get('lower_2', basis * 0.990))),
            ('lower_3', float(bands.get('lower_3', basis * 0.985))),
            ('lower_4', float(bands.get('lower_4', basis * 0.980))),
            ('lower_5', float(bands.get('lower_5', basis * 0.970))),
            ('lower_6', float(bands.get('lower_6', basis * 0.960))),
            ('lower_climax', float(bands.get('lower_6', basis * 0.960)) - (atr * 1.5))
        ]
        for i in range(len(levels) - 1):
            name_high, p_high = levels[i]
            name_low, p_low = levels[i + 1]
            if p_low <= current_price <= p_high or i == len(levels) - 2 and current_price <= p_low:
                span = max(1e-6, p_high - p_low)
                progress = max(0.0, min(1.0, (p_high - current_price) / span))
                if progress < 0.3333:
                    sub_idx = 1
                elif progress < 0.6666:
                    sub_idx = 2
                else:
                    sub_idx = 3

                if name_high == 'basis':
                    zone = 1
                elif name_high in ('lower_1', 'lower_2'):
                    zone = 2
                else:
                    zone = 3

                in_exhaustion = (sub_idx == 3) and (zone > 1)
                in_extreme = name_low in ('lower_5', 'lower_6', 'lower_climax') or (name_low == 'lower_4' and sub_idx == 3)

                return {
                    'interval': f"{name_high}_to_{name_low}",
                    'major_target': name_low,
                    'target_price': p_low,
                    'zone': zone,
                    'sub_band': sub_idx,
                    'progress_pct': round(progress * 100.0, 1),
                    'in_exhaustion_zone': in_exhaustion,
                    'in_extreme_zone': in_extreme,
                    'is_lower6': current_price <= float(bands.get('lower_6', 0))
                }

        return {
            'interval': 'above_basis',
            'major_target': 'basis',
            'target_price': basis,
            'zone': 1,
            'sub_band': 1,
            'progress_pct': 0.0,
            'in_exhaustion_zone': False,
            'in_extreme_zone': False,
            'is_lower6': False
        }


def evaluate_15m_ema_structure(df_15m: Optional[pd.DataFrame], side: str = 'long') -> dict:
    """
    EJE ESTRUCTURAL 15 MINUTOS (EMA3 vs EMA9 & Pendiente):
    Gobierna el ciclo de maduración y salidas en todas las zonas de Fibonacci.
    
    LONG:
      - is_trend_alive: EMA3 > EMA9, Slope(EMA3) > 0 y Close >= EMA9.
      - is_exhausted:   EMA3 <= EMA9 o Slope(EMA3) <= 0 o Close < EMA9.
    SHORT:
      - is_trend_alive: EMA3 < EMA9, Slope(EMA3) < 0 y Close <= EMA9.
      - is_exhausted:   EMA3 >= EMA9 o Slope(EMA3) >= 0 o Close > EMA9.
    """
    if df_15m is None or len(df_15m) < 5:
        return {
            'is_trend_alive': True, # En ausencia de suficientes datos, conceder beneficio de duda para no abortar
            'is_exhausted': False,
            'ema3': 0.0,
            'ema9': 0.0,
            'ema3_slope_pct': 0.0,
            'reason': 'Datos 15m insuficientes (<5 velas)'
        }

    try:
        close = _safe_col(df_15m, 'close')
        ema3 = close.ewm(span=3, adjust=False).mean()
        ema9 = close.ewm(span=9, adjust=False).mean()

        ema3_now = float(ema3.iloc[-1])
        ema3_prev = float(ema3.iloc[-2]) if len(ema3) >= 2 else ema3_now
        ema9_now = float(ema9.iloc[-1])
        c_now = float(close.iloc[-1])

        slope_pct = ((ema3_now - ema3_prev) / ema3_prev * 100.0) if ema3_prev > 0 else 0.0

        is_long = side.lower() in ('long', 'buy')
        if is_long:
            is_trend_alive = (ema3_now > ema9_now) and (slope_pct > 0.0) and (c_now >= ema9_now)
            is_exhausted = (ema3_now <= ema9_now) or (slope_pct <= 0.0) or (c_now < ema9_now)
            state_desc = "TENDENCIA VIVA" if is_trend_alive else ("AGOTAMIENTO" if is_exhausted else "NEUTRAL")
            return {
                'is_trend_alive': is_trend_alive,
                'is_exhausted': is_exhausted,
                'ema3': round(ema3_now, 4),
                'ema9': round(ema9_now, 4),
                'ema3_slope_pct': round(slope_pct, 4),
                'reason': (
                    f"15m LONG [{state_desc}]: EMA3({ema3_now:.2f}) {' > ' if ema3_now > ema9_now else ' <= '} EMA9({ema9_now:.2f}), "
                    f"Slope={slope_pct:+.3f}%, Close=${c_now:.2f}"
                )
            }
        else:
            is_trend_alive = (ema3_now < ema9_now) and (slope_pct < 0.0) and (c_now <= ema9_now)
            is_exhausted = (ema3_now >= ema9_now) or (slope_pct >= 0.0) or (c_now > ema9_now)
            state_desc = "TENDENCIA VIVA" if is_trend_alive else ("AGOTAMIENTO" if is_exhausted else "NEUTRAL")
            return {
                'is_trend_alive': is_trend_alive,
                'is_exhausted': is_exhausted,
                'ema3': round(ema3_now, 4),
                'ema9': round(ema9_now, 4),
                'ema3_slope_pct': round(slope_pct, 4),
                'reason': (
                    f"15m SHORT [{state_desc}]: EMA3({ema3_now:.2f}) {' < ' if ema3_now < ema9_now else ' >= '} EMA9({ema9_now:.2f}), "
                    f"Slope={slope_pct:+.3f}%, Close=${c_now:.2f}"
                )
            }

    except Exception as e:
        log_error(MODULE, f"Error evaluando estructura 15m EMA: {e}")
        return {
            'is_trend_alive': True,
            'is_exhausted': False,
            'ema3': 0.0,
            'ema9': 0.0,
            'ema3_slope_pct': 0.0,
            'reason': f"Error: {e}"
        }


def is_eod_final_candles(now_dt: Optional[datetime] = None) -> bool:
    """
    Determina si nos encontramos en el tramo final de las últimas 3 velas de 15m
    del horario intradía (15:15 ET a 15:50 ET).
    """
    from datetime import time as dt_time
    from zoneinfo import ZoneInfo
    if now_dt is None:
        try:
            now_dt = datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York'))
        except Exception:
            now_dt = datetime.now().astimezone(ZoneInfo('America/New_York'))
    elif now_dt.tzinfo is not None:
        try:
            now_dt = now_dt.astimezone(ZoneInfo('America/New_York'))
        except Exception:
            pass
    t = now_dt.time()
    return dt_time(15, 15) <= t < dt_time(15, 50)


def is_eod_hard_deadline(now_dt: Optional[datetime] = None) -> bool:
    """
    Determina si nos encontramos en el umbral estricto de cierre forzoso EOD (15:50 ET a 16:05 ET).
    A partir de las 15:50 ET, TODAS las posiciones de stocks se liquidan al 100% incondicionalmente
    para erradicar el riesgo nocturno y la dilución (Cero retención overnight).
    """
    from datetime import time as dt_time
    from zoneinfo import ZoneInfo
    if now_dt is None:
        try:
            now_dt = datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York'))
        except Exception:
            now_dt = datetime.now().astimezone(ZoneInfo('America/New_York'))
    elif now_dt.tzinfo is not None:
        try:
            now_dt = now_dt.astimezone(ZoneInfo('America/New_York'))
        except Exception:
            pass
    t = now_dt.time()
    return dt_time(15, 50) <= t <= dt_time(16, 5)


def evaluate_fuel_15m(df_15m: pd.DataFrame, side: str = 'long') -> dict:
    """
    Evalúa el Combustible Estructural en 15 minutos:
    - RVOL 15m (volumen actual vs media de 20 períodos)
    - Pendiente de volumen (Volume slope)
    - Calidad y dirección de la vela (SIPV)
    """
    if df_15m is None or len(df_15m) < 3:
        return {'state': 'NORMAL', 'rvol': 1.0, 'slope': 0.0, 'keep_room': False, 'reason': 'Datos 15m insuficientes'}

    try:
        vol = _safe_col(df_15m, 'volume')
        close = _safe_col(df_15m, 'close')
        open_p = _safe_col(df_15m, 'open')
        high = _safe_col(df_15m, 'high')
        low = _safe_col(df_15m, 'low')

        if len(vol) < 2 or vol.sum() == 0:
            return {'state': 'NORMAL', 'rvol': 1.0, 'slope': 0.0, 'keep_room': False, 'reason': 'Volumen 0 o ausente'}

        vol_mean = float(vol.rolling(20, min_periods=3).mean().iloc[-1])
        cur_vol = float(vol.iloc[-1])
        prev_vol = float(vol.iloc[-2])
        rvol = cur_vol / vol_mean if vol_mean > 0 else 1.0
        vol_slope = cur_vol - prev_vol

        c_now = float(close.iloc[-1])
        o_now = float(open_p.iloc[-1])
        h_now = float(high.iloc[-1])
        l_now = float(low.iloc[-1])
        rng = max(1e-6, h_now - l_now)
        body = abs(c_now - o_now)
        body_pct = body / rng

        is_long = side.lower() in ('long', 'buy')
        is_favorable_candle = (c_now > o_now) if is_long else (c_now < o_now)

        upper_wick = (h_now - max(c_now, o_now)) / rng
        lower_wick = (min(c_now, o_now) - l_now) / rng

        # 1. Clímax de Volumen (Absorción institucional / Techo de volumen)
        if rvol >= 2.2 and ((is_long and upper_wick >= 0.25) or (not is_long and lower_wick >= 0.25)):
            return {
                'state': 'CLIMAX_EXHAUSTION',
                'rvol': round(rvol, 2),
                'slope': round(vol_slope, 0),
                'keep_room': False,
                'reason': f"Clímax de volumen institucional ({rvol:.1f}x) con mecha de rechazo ({upper_wick*100:.1f}%)"
            }

        # 2. Combustible Fuerte (RVOL >= 1.2, vela a favor con cuerpo pleno)
        if rvol >= 1.2 and is_favorable_candle and body_pct >= 0.40 and vol_slope > 0:
            return {
                'state': 'HIGH_FUEL',
                'rvol': round(rvol, 2),
                'slope': round(vol_slope, 0),
                'keep_room': True,
                'reason': f"Combustible Fuerte en 15m (RVOL {rvol:.1f}x > 1.2, vela direccional). Proteger y guardar espacio."
            }

        # 3. Combustible Agotándose (Volumen secándose o decayendo)
        vol_decay = False
        if len(vol) >= 3:
            vol_decay = (vol.iloc[-1] < vol.iloc[-2] < vol.iloc[-3])

        if rvol < 0.75 or vol_decay or ((is_long and upper_wick >= 0.35) or (not is_long and lower_wick >= 0.35)):
            return {
                'state': 'EXHAUSTED',
                'rvol': round(rvol, 2),
                'slope': round(vol_slope, 0),
                'keep_room': False,
                'reason': f"Combustible Agotado en 15m (RVOL {rvol:.1f}x < 0.8 o volumen secándose). Alerta de salida."
            }

        return {
            'state': 'NORMAL',
            'rvol': round(rvol, 2),
            'slope': round(vol_slope, 0),
            'keep_room': False,
            'reason': f"Combustible Normal en 15m (RVOL {rvol:.1f}x)"
        }

    except Exception as e:
        log_error(MODULE, f"Error evaluando combustible 15m: {e}")
        return {'state': 'NORMAL', 'rvol': 1.0, 'slope': 0.0, 'keep_room': False, 'reason': f"Error: {e}"}


def evaluate_5m_micro_trigger(df_5m: pd.DataFrame, current_price: float, side: str = 'long') -> dict:
    """
    Micro-Gatillos de Precisión en 5 minutos:
    - Cruce EMA3 < EMA9 (para LONG) o EMA3 > EMA9 (para SHORT)
    - Pendiente de Banda Bollinger Superior en 5m (Slope <= 0)
    - Cierre por debajo de EMA3 en 5m
    """
    if df_5m is None or len(df_5m) < 5:
        return {'is_trigger': False, 'reason': 'Datos 5m insuficientes (<5 velas)'}

    try:
        close = _safe_col(df_5m, 'close')
        high = _safe_col(df_5m, 'high')
        low = _safe_col(df_5m, 'low')

        ema3 = close.ewm(span=3, adjust=False).mean()
        ema9 = close.ewm(span=9, adjust=False).mean()

        sma20 = close.rolling(20, min_periods=5).mean()
        std20 = close.rolling(20, min_periods=5).std().fillna(0)
        bb_upper = sma20 + (2.0 * std20)
        bb_lower = sma20 - (2.0 * std20)

        ema3_now = float(ema3.iloc[-1])
        ema3_prev = float(ema3.iloc[-2])
        ema9_now = float(ema9.iloc[-1])
        ema9_prev = float(ema9.iloc[-2])

        c_now = float(close.iloc[-1])
        h_now = float(high.iloc[-1])
        l_now = float(low.iloc[-1])

        bb_u_now = float(bb_upper.iloc[-1])
        bb_u_prev = float(bb_upper.iloc[-2])
        bb_u_slope = bb_u_now - bb_u_prev

        bb_l_now = float(bb_lower.iloc[-1])
        bb_l_prev = float(bb_lower.iloc[-2])
        bb_l_slope = bb_l_now - bb_l_prev

        is_long = side.lower() in ('long', 'buy')

        if is_long:
            # 1. Cruce bajista EMA3 < EMA9
            ema_crossed_down = (ema3_now < ema9_now)
            
            # 2. Bollinger Superior se aplanó o declinó tras tocarla
            bb_flattened = (bb_u_slope <= 0.0005) and (h_now >= bb_u_now * 0.995 or c_now >= bb_u_now * 0.990)

            # 3. Vela de 5m cerró por debajo de EMA3 tras impulso
            close_below_ema3 = (c_now < ema3_now)

            # 4. Pendiente de EMA3 negativa
            ema3_curling_down = (ema3_now < ema3_prev)

            if ema_crossed_down:
                return {
                    'is_trigger': True,
                    'trigger_type': 'EMA3_LT_EMA9',
                    'ema3': round(ema3_now, 4),
                    'ema9': round(ema9_now, 4),
                    'reason': f"Cruce bajista en 5m: EMA3 ({ema3_now:.2f}) < EMA9 ({ema9_now:.2f})"
                }

            if bb_flattened and close_below_ema3:
                return {
                    'is_trigger': True,
                    'trigger_type': 'BB_FLATTENED_CLOSE_UNDER_EMA3',
                    'ema3': round(ema3_now, 4),
                    'bb_slope': round(bb_u_slope, 4),
                    'reason': f"Bollinger 5m horizontal (slope {bb_u_slope:.4f} <= 0) con Close (${c_now:.2f}) < EMA3 (${ema3_now:.2f})"
                }

            if close_below_ema3 and ema3_curling_down and (h_now >= bb_u_now * 0.99):
                return {
                    'is_trigger': True,
                    'trigger_type': 'REJECTION_BB_EMA3_CURL',
                    'ema3': round(ema3_now, 4),
                    'reason': f"Rechazo en BB Superior 5m con EMA3 girando hacia abajo"
                }

            return {
                'is_trigger': False,
                'ema3': round(ema3_now, 4),
                'ema9': round(ema9_now, 4),
                'reason': f"Impulso 5m vigente: EMA3 ({ema3_now:.2f}) >= EMA9 ({ema9_now:.2f})"
            }

        else:
            # SHORT
            ema_crossed_up = (ema3_now > ema9_now)
            bb_flattened = (bb_l_slope >= -0.0005) and (l_now <= bb_l_now * 1.005)
            close_above_ema3 = (c_now > ema3_now)

            if ema_crossed_up:
                return {
                    'is_trigger': True,
                    'trigger_type': 'EMA3_GT_EMA9',
                    'reason': f"Cruce alcista en 5m: EMA3 > EMA9 para posición SHORT"
                }
            if bb_flattened and close_above_ema3:
                return {
                    'is_trigger': True,
                    'trigger_type': 'BB_LOWER_FLATTENED',
                    'reason': f"Bollinger Inferior 5m horizontal con Close > EMA3"
                }

            return {'is_trigger': False, 'reason': "Impulso SHORT vigente en 5m"}

    except Exception as e:
        log_error(MODULE, f"Error evaluando micro-gatillo 5m: {e}")
        return {'is_trigger': False, 'reason': f"Error: {e}"}


def evaluate_macro_bollinger_levels(
    current_price: float,
    df_1h: Optional[pd.DataFrame] = None,
    df_4h: Optional[pd.DataFrame] = None,
    df_1d: Optional[pd.DataFrame] = None,
    side: str = 'long'
) -> dict:
    """
    Evalúa la proximidad o toque de Bandas de Bollinger Macro (1H, 4H, 1D).
    """
    is_long = side.lower() in ('long', 'buy')
    res = {
        'hit_1h': False,
        'hit_4h': False,
        'hit_1d': False,
        'bb_1h_upper': 0.0,
        'bb_4h_upper': 0.0,
        'bb_1d_upper': 0.0,
        'bb_1h_flat': False,
        'macro_recommendation': 'NONE'
    }

    def _calc_bb(df):
        if df is None or len(df) < 20:
            return 0.0, 0.0, 0.0
        c = _safe_col(df, 'close')
        sma = float(c.rolling(20).mean().iloc[-1])
        std = float(c.rolling(20).std().iloc[-1])
        prev_sma = float(c.rolling(20).mean().iloc[-2]) if len(c) >= 21 else sma
        prev_std = float(c.rolling(20).std().iloc[-2]) if len(c) >= 21 else std
        up = sma + 2.0 * std
        lo = sma - 2.0 * std
        prev_up = prev_sma + 2.0 * prev_std
        slope_up = up - prev_up
        return up, lo, slope_up

    # 1. 1D
    up_1d, lo_1d, _ = _calc_bb(df_1d)
    if is_long and up_1d > 0 and current_price >= up_1d * 0.995:
        res['hit_1d'] = True
        res['bb_1d_upper'] = round(up_1d, 4)
        res['macro_recommendation'] = 'TP_TOTAL_100_1D'

    # 2. 4H
    up_4h, lo_4h, _ = _calc_bb(df_4h)
    if is_long and up_4h > 0 and current_price >= up_4h * 0.995:
        res['hit_4h'] = True
        res['bb_4h_upper'] = round(up_4h, 4)
        if res['macro_recommendation'] == 'NONE':
            res['macro_recommendation'] = 'TP_MAJOR_75_4H'

    # 3. 1H
    up_1h, lo_1h, slope_1h = _calc_bb(df_1h)
    if is_long and up_1h > 0:
        res['bb_1h_upper'] = round(up_1h, 4)
        if current_price >= up_1h * 0.995:
            res['hit_1h'] = True
            if res['macro_recommendation'] == 'NONE':
                res['macro_recommendation'] = 'TP_PARTIAL_50_1H'
        if slope_1h <= 0 and current_price >= up_1h * 0.985:
            res['bb_1h_flat'] = True

    return res


def evaluate_accelerated_trailing_stop(
    position: dict,
    current_price: float,
    df_5m: Optional[pd.DataFrame],
    bands_15m: dict,
    side: str = 'long'
) -> dict:
    """
    Trailing Stop Acelerado para Crecimiento Explosivo en UPPER_5 / UPPER_6 (LONG)
    o LOWER_5 / LOWER_6 (SHORT).
    1. Venta Parcial 50% al primer toque de UPPER_6 / LOWER_6.
    2. Piso de Ganancia bloqueado en UPPER_5 / LOWER_5.
    3. Trailing vela a vela en 5m anclado al Low[t-1] (LONG) o High[t-1] (SHORT).
    4. Cierre total si una vela de 5m cierra perforando EMA3.
    """
    is_long = side.lower() in ('long', 'buy')
    partial_taken = bool(position.get('tp_block1_executed') or position.get('climax_tp50_done'))

    if is_long:
        u5 = float(bands_15m.get('upper_5', 0))
        u6 = float(bands_15m.get('upper_6', 0))

        if u5 <= 0 or current_price < (u5 * 0.998):
            return {'action': 'NONE'}

        touched_u5 = current_price >= (u5 * 0.998)
        touched_u6 = (u6 > 0 and current_price >= (u6 * 0.998))
        entry_p = float(position.get('avg_price') or position.get('entry_price') or 0.0)
        gain_pct = ((current_price - entry_p) / entry_p * 100.0) if entry_p > 0 else 0.0

        if touched_u5 and not partial_taken and gain_pct >= 2.5:
            target_level = "UPPER_6" if touched_u6 else "UPPER_5"
            target_val = u6 if touched_u6 else u5
            return {
                'action': 'TAKE_PROFIT_50_CLIMAX',
                'pct': 50,
                'rule_code': f'ADUANA_STK_CLIMAX_{target_level}_TP50',
                'reason': f"Clímax en {target_level} (${target_val:.2f}) con ganancia +{gain_pct:.1f}%: Cierre parcial del 50% garantizado."
            }

        if df_5m is not None and len(df_5m) >= 2:
            lows = _safe_col(df_5m, 'low')
            closes = _safe_col(df_5m, 'close')
            ema3 = closes.ewm(span=3, adjust=False).mean()

            prev_low = float(lows.iloc[-2])
            cur_close = float(closes.iloc[-1])
            ema3_now = float(ema3.iloc[-1])

            if current_price < prev_low:
                return {
                    'action': 'CLOSE_TRAILING_LOW_BREAK',
                    'pct': 100,
                    'rule_code': 'ADUANA_STK_KINETIK_LOW_BREAK',
                    'reason': f"Trailing Acelerado 5m: Precio (${current_price:.2f}) perforó el Low de la vela previa (${prev_low:.2f}) en zona extrema."
                }

            if cur_close < ema3_now:
                return {
                    'action': 'CLOSE_TRAILING_EMA3_BREAK',
                    'pct': 100,
                    'rule_code': 'ADUANA_STK_KINETIK_EMA3_BREAK',
                    'reason': f"Trailing Acelerado 5m: Close (${cur_close:.2f}) perforó EMA3 (${ema3_now:.2f}) en zona extrema."
                }

        return {
            'action': 'MAINTAIN_KINETIK_TRAILING',
            'sl_floor': round(u5, 4),
            'reason': f"Trailing Acelerado Activo: Cabalgando zona extrema con piso protegido en UPPER_5 (${u5:.2f})"
        }
    else:
        # SHORT
        l5 = float(bands_15m.get('lower_5', 0))
        l6 = float(bands_15m.get('lower_6', 0))

        if l5 <= 0 or current_price > l5:
            return {'action': 'NONE'}

        touched_l6 = current_price <= l6 * 1.002
        if touched_l6 and not partial_taken:
            return {
                'action': 'TAKE_PROFIT_50_CLIMAX',
                'pct': 50,
                'rule_code': 'ADUANA_STK_CLIMAX_LOWER6_TP50',
                'reason': f"Clímax Parabólico en LOWER_6 (${l6:.2f}): Cierre parcial del 50% garantizado en la cumbre bajista."
            }

        if df_5m is not None and len(df_5m) >= 2:
            highs = _safe_col(df_5m, 'high')
            closes = _safe_col(df_5m, 'close')
            ema3 = closes.ewm(span=3, adjust=False).mean()

            prev_high = float(highs.iloc[-2])
            cur_close = float(closes.iloc[-1])
            ema3_now = float(ema3.iloc[-1])

            if current_price > prev_high:
                return {
                    'action': 'CLOSE_TRAILING_HIGH_BREAK',
                    'pct': 100,
                    'rule_code': 'ADUANA_STK_KINETIK_HIGH_BREAK',
                    'reason': f"Trailing Acelerado 5m SHORT: Precio (${current_price:.2f}) perforó el High de la vela previa (${prev_high:.2f}) en zona extrema."
                }

            if cur_close > ema3_now:
                return {
                    'action': 'CLOSE_TRAILING_EMA3_BREAK',
                    'pct': 100,
                    'rule_code': 'ADUANA_STK_KINETIK_EMA3_BREAK',
                    'reason': f"Trailing Acelerado 5m SHORT: Close (${cur_close:.2f}) perforó EMA3 (${ema3_now:.2f}) al alza."
                }

        return {
            'action': 'MAINTAIN_KINETIK_TRAILING',
            'sl_floor': round(l5, 4),
            'reason': f"Trailing Acelerado Activo SHORT: Cabalgando zona extrema con piso protegido en LOWER_5 (${l5:.2f})"
        }


def evaluate_alpha_runner_sharp_exit(
    position: dict,
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
) -> dict:
    """
    MOTOR AGUDO DE CIERRE DE POSICIÓN (SECCIÓN A - DISEÑO WFF / ALPHA RUNNERS):
    1. Temporalidad 1 Hora (Cierre Total / Parcial en Extremos):
       - 1a: Vela 1H cuyo HIGH > BB_Upper_1H y su tamaño (HIGH - LOW) es mayor que cada una
             de las 9 velas anteriores de 1H -> activa búsqueda de cierre total en 2a o 2b.
       - 1b: Cuando el precio llega al UPPER_6 en 1H -> Cierre parcial 50% inmediato (y remanente sujeto a 2a/2b/2d).
    2. Temporalidad 15m y 5m:
       - 2a: Vela 15m con Close/High > BB_Upper_15m + mecha superior >= 15% del rango (High-Low)
             + precio toca el OPEN de 15m terminando en rojo (current_price <= Open_15m).
       - 2b: En 5m, OPEN > BB_Upper_5m + mecha superior >= 15% del rango (High-Low en 15m o 5m)
             + precio toca el OPEN de 5m en rojo (current_price <= Open_5m).
       - 2c: Si precio > BB_Upper, el Trailing Stop se mueve a (OPEN - Delta).
       - 2d: 3 Características de deterioro:
             * 2d-1: EMA3_15m reduce su pendiente o deja de ser ascendente -> vigila 2a y 2b.
             * 2d-2: BB_Upper_15m deja de subir (slope <= 0) o BB_Lower_15m empieza a subir (slope >= 0) -> vigila 2a y 2b.
             * 2d-3: En 5m, las velas abren con OPEN > BB_Upper_5m; mientras sean verdes (Close > Open) -> HOLD,
                     pero al PRIMER ROJO (current_price <= Open_5m) -> cerrar posición inmediatamente al tocar OPEN.
    """
    res = {
        'should_close': False,
        'action': 'HOLD',
        'pct_to_close': 0,
        'rule_code': 'NONE',
        'reason': '',
        'climax_1h_1a': False,
        'deterioration_2d1': False,
        'deterioration_2d2': False,
        'suggested_tsl_2c': 0.0,
    }
    if not position or current_price <= 0:
        return res

    side = str(position.get('side', 'long')).lower()
    if side not in ('long', 'buy'):
        return res

    entry_p = float(position.get('avg_price') or position.get('entry_price') or 0.0)
    shares = int(float(position.get('shares_remaining') or position.get('shares') or 0))
    if entry_p <= 0 or shares <= 0:
        return res

    gain_pct = (current_price - entry_p) / entry_p * 100.0
    pnl_usd = (current_price - entry_p) * shares
    group_name = str(position.get('group_name', '') or position.get('pool_type', '')).upper()
    rule_pos = str(position.get('rule_code', '') or position.get('strategy', '')).upper()
    is_alpha_runner = ('ALPHA_RUNNER' in group_name) or ('ALPHA' in rule_pos) or ('PULLBACK_' in rule_pos) or ('EMR_' in rule_pos) or ('MOMENTUM' in rule_pos)
    partial_done = bool(position.get('tp_block1_executed') or position.get('tp_1h_executed'))

    # Antigüedad de la posición en minutos (Mínimo de maduración 15 minutos salvo clímax >= 2.5%)
    entry_time_str = position.get('first_buy_at') or position.get('entry_time')
    age_mins = 0.0
    if entry_time_str:
        try:
            entry_dt = datetime.fromisoformat(str(entry_time_str).replace('Z', '+00:00'))
            age_mins = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 60.0
        except Exception:
            age_mins = 0.0

    # ── 1. EVALUACIÓN 1 HORA (1a y 1b) ──
    climax_1h_1a = False
    if df_1h is not None and len(df_1h) >= 10:
        try:
            c1h = _safe_col(df_1h, 'close')
            h1h = _safe_col(df_1h, 'high')
            l1h = _safe_col(df_1h, 'low')

            sma20_1h = float(c1h.rolling(20, min_periods=10).mean().iloc[-1])
            std20_1h = float(c1h.rolling(20, min_periods=10).std().fillna(0).iloc[-1])
            bb_up_1h = sma20_1h + 2.0 * std20_1h

            cur_h_1h = max(float(h1h.iloc[-1]), current_price)
            cur_l_1h = min(float(l1h.iloc[-1]), current_price)
            cur_range_1h = cur_h_1h - cur_l_1h

            # Rango de las 9 velas anteriores de 1H
            prev_9_ranges = (h1h.iloc[-10:-1] - l1h.iloc[-10:-1]).values
            max_prev_9_range = float(np.max(prev_9_ranges)) if len(prev_9_ranges) > 0 else 0.0

            # Condición 1a: High_1H > BB_Upper_1H y tamaño actual > las 9 velas previas
            if bb_up_1h > 0 and cur_h_1h > bb_up_1h and max_prev_9_range > 0 and cur_range_1h > max_prev_9_range:
                climax_1h_1a = True
                res['climax_1h_1a'] = True

            # Condición 1b: Precio llega al UPPER_6 en 1 Hora
            fib_1h = calculate_fibonacci_bands(df_1h, current_price)
            upper_6_1h = float(fib_1h.get('upper_6') or 0.0)
            if upper_6_1h > 0 and current_price >= upper_6_1h * 0.998 and gain_pct >= 1.5:
                if not partial_done and shares >= 2:
                    res.update({
                        'should_close': True,
                        'action': 'CLOSE_PARTIAL_50',
                        'pct_to_close': 50,
                        'shares_to_close': max(1, int(shares * 0.5)),
                        'rule_code': 'ALPHA_EXIT_1B_UPPER6_1H_TP50',
                        'reason': (
                            f"Regla 1b (1H UPPER_6): Precio (${current_price:.2f}) alcanzó UPPER_6 de 1H (${upper_6_1h:.2f}). "
                            f"Cierre parcial 50% (+{gain_pct:.2f}%), remanente vigilado por 2a/2b/2d."
                        )
                    })
                    return res
        except Exception as e1h:
            log_warning(MODULE, f"Error en evaluación 1H (1a/1b): {e1h}")

    # ── 2. EVALUACIÓN 15 MINUTOS (2d-1, 2d-2, 2a, 2c) ──
    deterioration_2d1 = False
    deterioration_2d2 = False
    wick_15m_pct = 0.0
    open_15m_cur = 0.0
    bb_up_15m_cur = 0.0

    if df_15m is not None and len(df_15m) >= 6:
        try:
            c15 = _safe_col(df_15m, 'close')
            o15 = _safe_col(df_15m, 'open')
            h15 = _safe_col(df_15m, 'high')
            l15 = _safe_col(df_15m, 'low')

            ema3_15 = c15.ewm(span=3, adjust=False).mean()
            slope_ema3_now = float(ema3_15.iloc[-1] - ema3_15.iloc[-2])
            slope_ema3_prev = float(ema3_15.iloc[-2] - ema3_15.iloc[-3])

            # 2d-1: EMA3 en 15m reduce su pendiente o deja de ser creciente/ascendente
            if slope_ema3_now <= 0 or (slope_ema3_prev > 0 and slope_ema3_now < slope_ema3_prev * 0.85):
                deterioration_2d1 = True
                res['deterioration_2d1'] = True

            # Bollinger 15m
            sma20_15 = c15.rolling(20, min_periods=5).mean()
            std20_15 = c15.rolling(20, min_periods=5).std().fillna(0)
            bb_up_15 = sma20_15 + 2.0 * std20_15
            bb_lo_15 = sma20_15 - 2.0 * std20_15

            bb_up_15m_cur = float(bb_up_15.iloc[-1])
            bb_up_slope_15 = float(bb_up_15.iloc[-1] - bb_up_15.iloc[-2])
            bb_lo_slope_15 = float(bb_lo_15.iloc[-1] - bb_lo_15.iloc[-2])

            # 2d-2: Banda superior se diluye (slope <= 0) o banda inferior empieza a ser positiva (slope >= 0)
            if bb_up_slope_15 <= 0 or bb_lo_slope_15 >= 0:
                deterioration_2d2 = True
                res['deterioration_2d2'] = True

            # Datos de la vela 15m actual y previa
            open_15m_cur = float(o15.iloc[-1])
            high_15m_cur = max(float(h15.iloc[-1]), current_price)
            low_15m_cur = min(float(l15.iloc[-1]), current_price)
            rng_15m_cur = max(1e-6, high_15m_cur - low_15m_cur)
            top_body_15m = max(open_15m_cur, current_price)
            wick_15m_pct = (high_15m_cur - top_body_15m) / rng_15m_cur

            # También revisar si la vela cerrada previa de 15m cerró > BB_Upper con mecha >= 15%
            prev_c15 = float(c15.iloc[-2])
            prev_o15 = float(o15.iloc[-2])
            prev_h15 = float(h15.iloc[-2])
            prev_l15 = float(l15.iloc[-2])
            prev_bb_up15 = float(bb_up_15.iloc[-2])
            prev_rng15 = max(1e-6, prev_h15 - prev_l15)
            prev_wick15_pct = (prev_h15 - max(prev_o15, prev_c15)) / prev_rng15

            # 2c: Si precio > BB_Upper_15m, sugerir Trailing Stop en (Open_15m - Delta)
            atr_15 = float((h15 - l15).rolling(14, min_periods=3).mean().iloc[-1])
            delta_15 = max(0.01, min(current_price * 0.003, 0.15 * atr_15))
            if bb_up_15m_cur > 0 and (current_price > bb_up_15m_cur or high_15m_cur > bb_up_15m_cur):
                cand_2c = round(open_15m_cur - delta_15, 2)
                if cand_2c > entry_p and cand_2c < current_price:
                    res['suggested_tsl_2c'] = max(res['suggested_tsl_2c'], cand_2c)

            # 2b-CLIMAX: Clímax Multivariable Refinado y Salidas Escalonadas (Salida 1, 2 y 3):
            try:
                from ta.momentum import RSIIndicator
                rsi_15m_val = float(RSIIndicator(c15, window=14).rsi().iloc[-1]) if len(c15) >= 14 else 50.0
                prev_9_rngs = (h15.iloc[-10:-1] - l15.iloc[-10:-1]).values if len(h15) >= 10 else []
                avg_9_rng = float(np.mean(prev_9_rngs)) if len(prev_9_rngs) > 0 else 0.0

                # -------------------------------------------------------------
                # SALIDA 3: CLÍMAX EXTREMO PARABÓLICO (RSI_15m >= 85.0) -> CIERRE TOTAL 100%
                # -------------------------------------------------------------
                if rsi_15m_val >= 85.0 and gain_pct >= 6.0:
                    return {
                        **res,
                        'should_close': True,
                        'action': 'CLOSE_TOTAL',
                        'pct_to_close': 100,
                        'shares_to_close': shares,
                        'rule_code': 'ALPHA_EXIT_CLIMAX_EXTREME_RSI85',
                        'reason': (
                            f"🚀 SALIDA 3 - CLÍMAX EXTREMO: RSI 15m ({rsi_15m_val:.1f} >= 85.0). "
                            f"Agotamiento comprador máximo (Blow-off Top). Cierre TOTAL 100% ({shares} sh @ ${current_price:.2f}, +{gain_pct:.1f}%)."
                        )
                    }

                # Fibonacci bands 15m
                fib_15 = calculate_fibonacci_bands(df_15m, current_price)
                upper_6_15 = float(fib_15.get('upper_6') or 0.0)
                touched_upper6 = (upper_6_15 > 0 and current_price >= upper_6_15 * 0.995 and gain_pct >= 6.0)

                is_2x_rejection_climax = (
                    avg_9_rng > 0 and rng_15m_cur >= 2.0 * avg_9_rng and
                    wick_15m_pct >= 0.10 and gain_pct >= 6.0 and
                    bb_up_15m_cur > 0 and high_15m_cur >= bb_up_15m_cur * 0.995
                )
                is_rsi_80_climax = (rsi_15m_val >= 80.0 and gain_pct >= 4.0)

                # -------------------------------------------------------------
                # SALIDA 1: CLÍMAX INICIAL (RSI >= 80, BB Upper o UPPER_6) -> VENTA PARCIAL 50%
                # -------------------------------------------------------------
                if (is_2x_rejection_climax or is_rsi_80_climax or touched_upper6) and not partial_done and shares >= 2:
                    shares_sell = max(1, int(shares * 0.50))
                    climax_type = (
                        f"RSI 15m ({rsi_15m_val:.1f} >= 80)" if is_rsi_80_climax else
                        (f"Vela 15m 2x (${rng_15m_cur:.2f} >= 2x ${avg_9_rng:.2f}) c/Mecha {wick_15m_pct*100:.1f}%" if is_2x_rejection_climax else f"Fibonacci UPPER_6 (${upper_6_15:.2f})")
                    )
                    # Ceñir Trailing Ratchet de inmediato al Low de la vela de clímax o EMA3_15m
                    ema3_15_val = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
                    climax_ratchet_sl = max(res.get('suggested_tsl_2c', 0.0), round(min(low_15m_cur, ema3_15_val), 2))
                    if climax_ratchet_sl > entry_p:
                        res['suggested_tsl_2c'] = climax_ratchet_sl

                    return {
                        **res,
                        'should_close': True,
                        'action': 'CLOSE_PARTIAL_50',
                        'pct_to_close': 50,
                        'shares_to_close': shares_sell,
                        'rule_code': 'ALPHA_EXIT_CLIMAX_MULTIVARIABLE_TP50',
                        'reason': (
                            f"🎯 SALIDA 1 - CLÍMAX INICIAL ({climax_type}): Ganancia actual +{gain_pct:.2f}%. "
                            f"Venta parcial del 50% ({shares_sell} sh @ ${current_price:.2f}), stop ceñido a ${climax_ratchet_sl:.2f} (Low Clímax/EMA3)."
                        )
                    }

                # -------------------------------------------------------------
                # SALIDA 2: RANGE DECAY / CONTRACCIÓN DE RANGO POST-CLÍMAX -> CIERRE TOTAL 100%
                # -------------------------------------------------------------
                if partial_done and len(h15) >= 2:
                    prev_rng15 = max(1e-6, float(h15.iloc[-2]) - float(l15.iloc[-2]))
                    range_ratio = rng_15m_cur / prev_rng15
                    ema3_15_val = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
                    lost_ema3 = (current_price < ema3_15_val * 0.995)
                    is_range_decay = (range_ratio < 0.75) and (current_price <= open_15m_cur * 0.998 or low_15m_cur < float(l15.iloc[-2]) or wick_15m_pct >= 0.20)

                    if is_range_decay or lost_ema3:
                        decay_reason = f"Rango 15m (${rng_15m_cur:.2f}) < 75% del previo (${prev_rng15:.2f}) con rechazo" if is_range_decay else f"Pérdida de EMA3 15m (${ema3_15_val:.2f})"
                        return {
                            **res,
                            'should_close': True,
                            'action': 'CLOSE_TOTAL',
                            'pct_to_close': 100,
                            'shares_to_close': shares,
                            'rule_code': 'ALPHA_EXIT_RANGE_DECAY_POST_CLIMAX',
                            'reason': (
                                f"🛑 SALIDA 2 - CONTRACCIÓN DE RANGO (Range Decay): {decay_reason}. "
                                f"Cierre TOTAL remanente ({shares} sh @ ${current_price:.2f}, +{gain_pct:.1f}%)."
                            )
                        }
            except Exception as e_climax:
                log_debug(MODULE, f"Error evaluando Clímax Multivariable 15m: {e_climax}")

            # -----------------------------------------------------------------
            # GATILLO DE SALIDA CLÍMAX POR RECHAZO BOLLINGER (ADUANA_CLIMAX_BB_REJECTION)
            # Vela 15m con OPEN >= BB_Upper_15m * 0.995 (abrió fuera o sobre banda superior)
            # + Fuerte mecha superior de rechazo (upper_wick >= max(0.15, body * 1.5) o wick/range >= 0.40)
            # -----------------------------------------------------------------
            body_15m_cur = abs(current_price - open_15m_cur)
            top_body_15m_cur = max(open_15m_cur, current_price)
            upper_wick_15m_cur = high_15m_cur - top_body_15m_cur
            cur_wick_ratio = upper_wick_15m_cur / rng_15m_cur if rng_15m_cur > 0 else 0.0
            cur_opened_above_bb = (bb_up_15m_cur > 0 and open_15m_cur >= bb_up_15m_cur * 0.995)
            cur_has_strong_rejection = (upper_wick_15m_cur >= max(0.15, body_15m_cur * 1.5)) or (cur_wick_ratio >= 0.40)
            is_cur_bb_rejection = cur_opened_above_bb and cur_has_strong_rejection

            prev_body_15m = abs(prev_c15 - prev_o15)
            prev_top_15m = max(prev_o15, prev_c15)
            prev_upper_wick_15m = prev_h15 - prev_top_15m
            prev_wick_ratio = prev_upper_wick_15m / prev_rng15 if prev_rng15 > 0 else 0.0
            prev_opened_above_bb = (prev_bb_up15 > 0 and prev_o15 >= prev_bb_up15 * 0.995)
            prev_has_strong_rejection = (prev_upper_wick_15m >= max(0.15, prev_body_15m * 1.5)) or (prev_wick_ratio >= 0.40)
            is_prev_bb_rejection = prev_opened_above_bb and prev_has_strong_rejection and (current_price <= prev_top_15m * 1.002)

            if (is_cur_bb_rejection or is_prev_bb_rejection) and gain_pct >= 2.5:
                close_total = (is_alpha_runner or partial_done or shares < 2 or gain_pct >= 6.0)
                pct = 100 if close_total else 50
                shares_to_sell = shares if pct == 100 else max(1, int(shares * 0.5))
                candle_desc = "Vela actual 15m" if is_cur_bb_rejection else "Vela previa 15m"
                wick_pct_disp = (cur_wick_ratio if is_cur_bb_rejection else prev_wick_ratio) * 100.0
                open_ref = open_15m_cur if is_cur_bb_rejection else prev_o15
                bb_ref = bb_up_15m_cur if is_cur_bb_rejection else prev_bb_up15
                return {
                    **res,
                    'should_close': True,
                    'action': 'CLOSE_TOTAL' if pct == 100 else 'CLOSE_PARTIAL_50',
                    'pct_to_close': pct,
                    'shares_to_close': shares_to_sell,
                    'rule_code': 'ADUANA_CLIMAX_BB_REJECTION',
                    'gain_pct': round(gain_pct, 2),
                    'pnl_usd': round(pnl_usd, 2),
                    'reason': (
                        f"🚨 ADUANA CLÍMAX (Rechazo en Bollinger Superior): {candle_desc} abrió sobre BB Superior "
                        f"(Open ${open_ref:.2f} >= BB_Upper ${bb_ref:.2f}) con fuerte mecha de rechazo ({wick_pct_disp:.1f}% del rango). "
                        f"Cierre {pct}% asegurando +{gain_pct:.2f}% de ganancia."
                    )
                }

            # Condición 2a:
            # Vela de 15m supera BB_Upper_15m (prev_c15 > prev_bb_up15 o high_15m_cur > bb_up_15m_cur),
            # forma mecha superior >= 15% del rango (High - Low),
            # y el precio toca el OPEN de 15m volviendo la vela roja (current_price <= open_15m_cur).
            above_bb_15m = (bb_up_15m_cur > 0 and (high_15m_cur > bb_up_15m_cur or prev_c15 > prev_bb_up15))
            has_15pct_wick_15m = (wick_15m_pct >= 0.15) or (prev_wick15_pct >= 0.15)
            touched_open_15m_red = (current_price <= open_15m_cur)
            if above_bb_15m and has_15pct_wick_15m and touched_open_15m_red and (gain_pct >= 2.5 or (gain_pct >= 0.8 and age_mins >= 15.0)):
                close_total = (is_alpha_runner or climax_1h_1a or partial_done or deterioration_2d1 or deterioration_2d2 or shares < 2)
                pct = 100 if close_total else 50
                return {
                    **res,
                    'should_close': True,
                    'action': 'CLOSE_TOTAL' if pct == 100 else 'CLOSE_PARTIAL_50',
                    'pct_to_close': pct,
                    'shares_to_close': shares if pct == 100 else max(1, int(shares * 0.5)),
                    'rule_code': 'ALPHA_EXIT_2A_15M_WICK15_OPEN_RED',
                    'reason': (
                        f"Regla 2a (15m > BB_Upper + Mecha {max(wick_15m_pct, prev_wick15_pct)*100:.1f}% >= 15% + Toque OPEN en Rojo): "
                        f"Precio (${current_price:.2f}) <= Open_15m (${open_15m_cur:.2f}) "
                        f"[1a={climax_1h_1a}, 2d1={deterioration_2d1}, 2d2={deterioration_2d2}]. Cierre {pct}% (+{gain_pct:.2f}%)."
                    )
                }
        except Exception as e15:
            log_warning(MODULE, f"Error en evaluación 15m (2a/2d): {e15}")

    # ── 3. EVALUACIÓN 5 MINUTOS (2b, 2c, 2d-3) ──
    if df_5m is not None and len(df_5m) >= 6:
        try:
            c5 = _safe_col(df_5m, 'close')
            o5 = _safe_col(df_5m, 'open')
            h5 = _safe_col(df_5m, 'high')
            l5 = _safe_col(df_5m, 'low')

            sma20_5 = c5.rolling(20, min_periods=5).mean()
            std20_5 = c5.rolling(20, min_periods=5).std().fillna(0)
            bb_up_5 = sma20_5 + 2.0 * std20_5

            bb_up_5m_cur = float(bb_up_5.iloc[-1])
            open_5m_cur = float(o5.iloc[-1])
            high_5m_cur = max(float(h5.iloc[-1]), current_price)
            low_5m_cur = min(float(l5.iloc[-1]), current_price)
            rng_5m_cur = max(1e-6, high_5m_cur - low_5m_cur)
            wick_5m_pct = (high_5m_cur - max(open_5m_cur, current_price)) / rng_5m_cur

            atr_5 = float((h5 - l5).rolling(14, min_periods=3).mean().iloc[-1])
            delta_5 = max(0.01, min(current_price * 0.0025, 0.15 * atr_5))

            # 2c en 5m: Si precio > BB_Upper_5m, mover TSL a (Open_5m - Delta)
            if bb_up_5m_cur > 0 and (current_price > bb_up_5m_cur or open_5m_cur > bb_up_5m_cur):
                cand_2c_5m = round(open_5m_cur - delta_5, 2)
                if cand_2c_5m > entry_p and cand_2c_5m < current_price:
                    res['suggested_tsl_2c'] = max(res['suggested_tsl_2c'], cand_2c_5m)

            # Condición 2d-3 (Seguimiento a minuto cuando 5m abre OPEN > BB_Upper_5m):
            # Mientras sea verde (current_price > open_5m_cur) -> HOLD.
            # Al PRIMER ROJO (current_price <= open_5m_cur cuando abrio sobre BB_Upper_5m):
            # Requiere 15 min de maduración salvo ganancia de clímax >= 2.5%
            if bb_up_5m_cur > 0 and open_5m_cur > bb_up_5m_cur:
                if current_price <= open_5m_cur and (gain_pct >= 2.5 or (gain_pct >= 0.5 and age_mins >= 15.0)):
                    return {
                        **res,
                        'should_close': True,
                        'action': 'CLOSE_TOTAL',
                        'pct_to_close': 100,
                        'shares_to_close': shares,
                        'rule_code': 'ALPHA_EXIT_2D3_5M_OPEN_ABOVE_BB_FIRST_RED',
                        'reason': (
                            f"Regla 2d-3 (5m Open ${open_5m_cur:.2f} > BB_Upper ${bb_up_5m_cur:.2f} + Primer Giro Rojo): "
                            f"Precio (${current_price:.2f}) tocó el OPEN de 5m (${open_5m_cur:.2f}). "
                            f"Cierre Total inmediato asegurando +{gain_pct:.2f}%."
                        )
                    }

            # Condición 2b:
            # En 5m, Open > BB_Upper_5m (o la vela previa de 5m abrió > BB_Upper_5m),
            # mecha >= 15% en 15m o 5m, y el precio toca el OPEN de 5m terminando en rojo.
            # Requiere 15 min de maduración salvo ganancia de clímax >= 2.5%
            prev_o5 = float(o5.iloc[-2])
            prev_bb_up5 = float(bb_up_5.iloc[-2])
            opened_above_bb5 = (bb_up_5m_cur > 0 and (open_5m_cur > bb_up_5m_cur or prev_o5 > prev_bb_up5))
            has_15pct_wick = (wick_15m_pct >= 0.15) or (wick_5m_pct >= 0.15)
            touched_open_5m_red = (current_price <= open_5m_cur)

            if opened_above_bb5 and has_15pct_wick and touched_open_5m_red and (gain_pct >= 2.5 or (gain_pct >= 0.6 and age_mins >= 15.0)):
                close_total = (is_alpha_runner or climax_1h_1a or partial_done or deterioration_2d1 or deterioration_2d2 or shares < 2)
                pct = 100 if close_total else 50
                return {
                    **res,
                    'should_close': True,
                    'action': 'CLOSE_TOTAL' if pct == 100 else 'CLOSE_PARTIAL_50',
                    'pct_to_close': pct,
                    'shares_to_close': shares if pct == 100 else max(1, int(shares * 0.5)),
                    'rule_code': 'ALPHA_EXIT_2B_5M_WICK15_OPEN_RED',
                    'reason': (
                        f"Regla 2b (5m Open > BB_Upper + Mecha >= 15% + Toque OPEN 5m en Rojo): "
                        f"Precio (${current_price:.2f}) <= Open_5m (${open_5m_cur:.2f}). Cierre {pct}% (+{gain_pct:.2f}%)."
                    )
                }
        except Exception as e5:
            log_warning(MODULE, f"Error en evaluación 5m (2b/2d-3): {e5}")

    return res


def calculate_ipo_super_runner_trailing_stop(
    position: dict,
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    now_dt: Optional[datetime] = None,
) -> dict:
    """
    TRAILING STOP PARA FAST-TRACK IPO SUPER-RUNNERS (5 MINUTOS):
    - Stop Loss inicial fijado debajo de (EMA9_5m - Delta).
    - Conforme aparece cada vela verde en 5m (Close_5m > Open_5m),
      el Trailing Stop se actualiza ratcheteando hacia arriba a (EMA9_5m - Delta).
    - En velas rojas (Close <= Open) o doji, el stop NO se reduce (es unidireccional ascendente).
    - Si el precio perfora el Trailing Stop, se activa la salida.
    """
    current_sl = float(position.get('stop_loss') or 0.0)
    current_tsl = float(position.get('trailing_sl_price') or current_sl)
    entry_p = float(position.get('avg_price') or position.get('entry_price') or 0.0)
    best_sl = max(current_sl, current_tsl)

    if entry_p <= 0 or current_price <= 0 or df_5m is None or len(df_5m) < 3:
        return {'should_update': False, 'new_sl': best_sl, 'stage': 'NONE', 'reason': 'Datos 5m insuficientes'}

    try:
        c5 = _safe_col(df_5m, 'close')
        o5 = _safe_col(df_5m, 'open')
        h5 = _safe_col(df_5m, 'high')
        l5 = _safe_col(df_5m, 'low')

        ema9_5 = float(c5.ewm(span=9, adjust=False).mean().iloc[-1])
        atr5 = float((h5 - l5).rolling(14, min_periods=3).mean().iloc[-1])
        delta = max(0.01, min(current_price * 0.0035, 0.15 * atr5 if atr5 > 0 else 0.05))

        # Comprobar si la vela actual o previa de 5m es verde (Close > Open)
        cur_c = float(c5.iloc[-1])
        cur_o = float(o5.iloc[-1])
        is_cur_green = (cur_c > cur_o) or (current_price > cur_o)

        prev_c = float(c5.iloc[-2]) if len(c5) >= 2 else cur_c
        prev_o = float(o5.iloc[-2]) if len(o5) >= 2 else cur_o
        is_prev_green = (prev_c > prev_o)

        if is_cur_green or is_prev_green:
            cand_sl = round(ema9_5 - delta, 2)
            if cand_sl > best_sl and cand_sl < current_price:
                best_sl = cand_sl
                return {
                    'should_update': True,
                    'new_sl': best_sl,
                    'stage': 'IPO_TRAIL_EMA9_5M_GREEN_CANDLE',
                    'reason': f"IPO Super-Runner Vela Verde 5m: SL elevado a EMA9_5m (${ema9_5:.2f})-Δ=${best_sl:.2f}"
                }

        return {'should_update': False, 'new_sl': best_sl, 'stage': 'IPO_HOLD', 'reason': 'Vela no verde o SL ya óptimo'}
    except Exception as e:
        log_warning("IPO_EXIT", f"Error calculando trailing stop IPO: {e}")
        return {'should_update': False, 'new_sl': best_sl, 'stage': 'ERROR', 'reason': str(e)}


def calculate_alpha_escalating_trailing_stop(
    position: dict,
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    now_dt: Optional[datetime] = None,
) -> dict:
    """
    SECCIÓN B.5 & 2C — TRAILING STOP ESCALONADO EN 3 ETAPAS + DOBLE CONTROL:
    Aplica a entradas 3a, 4a, 4b, 4c, 4d y activos ALPHA_RUNNER:
    - Regla 2c (Inmediata si Precio > BB_Upper):
      Trailing Stop sube a (OPEN - Delta).
    - Pasadas 3 velas de 5 minutos (>= 15 minutos desde la compra):
      * Etapa 1 (Mínima Ganancia 5m): Se coloca en el OPEN de la vela de 5m cuyo OPEN > precio de compra.
      * Etapa 2 (Tendencia Media 15m): Se coloca en (EMA9_15m - Delta).
      * Etapa 3 (Aceleración Parabólica 15m): Cuando (OPEN > BB_Upper) y (CLOSE > OPEN),
        se mueve agresivamente a (EMA3_15m - Delta).
    El ratchet es estrictamente unidireccional: new_tsl = max(current_sl, current_tsl, candidatos).
    """
    current_sl = float(position.get('stop_loss') or 0.0)
    current_tsl = float(position.get('trailing_sl_price') or current_sl)
    entry_p = float(position.get('avg_price') or position.get('entry_price') or 0.0)

    if entry_p <= 0 or current_price <= 0:
        return {'should_update': False, 'new_sl': current_sl, 'stage': 'NONE', 'reason': 'Precios inválidos'}

    # Calcular antigüedad en minutos
    entry_time_str = position.get('first_buy_at') or position.get('entry_time')
    age_mins = 0.0
    if entry_time_str:
        try:
            entry_dt = datetime.fromisoformat(str(entry_time_str).replace('Z', '+00:00'))
            ref_now = now_dt if now_dt is not None else datetime.now(timezone.utc)
            if getattr(ref_now, 'tzinfo', None) is not None and getattr(entry_dt, 'tzinfo', None) is not None:
                age_mins = (ref_now - entry_dt).total_seconds() / 60.0
            else:
                age_mins = (ref_now.replace(tzinfo=None) - entry_dt.replace(tzinfo=None)).total_seconds() / 60.0
        except Exception:
            age_mins = 0.0

    best_sl = max(current_sl, current_tsl)
    active_stage = 'INITIAL'
    reasons = []

    # ── IPO SUPER-RUNNER FAST-TRACK TRAILING STOP (EMA9_5m - Delta en velas verdes) ──
    group_name = str(position.get('group_name', '') or position.get('pool_type', '')).upper()
    rule_pos = str(position.get('rule_code', '') or position.get('strategy', '')).upper()
    is_ipo = ('IPO' in group_name) or ('IPO' in rule_pos)
    if is_ipo and df_5m is not None and len(df_5m) >= 3:
        ipo_res = calculate_ipo_super_runner_trailing_stop(position, current_price, df_5m, now_dt)
        if ipo_res.get('should_update'):
            return ipo_res

    try:
        # Calcular Delta dinámico basado en ATR de 15m/5m
        delta = max(0.01, round(current_price * 0.0025, 4))
        if df_15m is not None and len(df_15m) >= 5:
            h15 = _safe_col(df_15m, 'high')
            l15 = _safe_col(df_15m, 'low')
            atr15 = float((h15 - l15).rolling(14, min_periods=3).mean().iloc[-1])
            if atr15 > 0:
                delta = max(0.01, min(current_price * 0.0035, 0.15 * atr15))

        # ── Determinación previa de High Máximo alcanzado ──
        highest_seen = float(position.get('trail_high') or position.get('highest_price_reached') or current_price)
        if df_5m is not None and len(df_5m) > 0:
            h5_series = _safe_col(df_5m, 'high')
            if len(h5_series) > 0:
                highest_seen = max(highest_seen, float(h5_series.max()))

        # ── RATCHET A BREAKEVEN (CENTRO DE COSTO + 1%) AL ALCANZAR +4.0% ──
        if entry_p > 0 and highest_seen >= (entry_p * 1.04):
            be_sl_plus1 = round(entry_p * 1.01, 2)
            if be_sl_plus1 > best_sl and be_sl_plus1 < current_price:
                best_sl = be_sl_plus1
                active_stage = 'STAGE_RATCHET_BREAKEVEN_PLUS1'
                reasons.append(f"RatchetBE+1%(Entry ${entry_p:.2f}->High ${highest_seen:.2f}=>${be_sl_plus1:.2f})")

        # ── RATCHET DEL 80% SOBRE EL AVANCE DEL OPEN (Propuesta Aprobada) ──
        # Si el activo ha tenido una expansión >= 8% sobre el precio OPEN del día,
        # se fija un Stop inamovible que retiene al menos el 80% de ese recorrido:
        # Ratchet = Open_Day + 0.80 * (High_maximo - Open_Day)
        open_day = float(position.get('candle_open_day') or 0.0)
        if open_day <= 0 and df_5m is not None and len(df_5m) > 0:
            open_day = float(_safe_col(df_5m, 'open').iloc[0])
        if open_day <= 0:
            open_day = entry_p

        if open_day > 0 and highest_seen >= (open_day * 1.08):
            ratchet_sl_80 = round(open_day + 0.80 * (highest_seen - open_day), 2)
            if ratchet_sl_80 > best_sl and ratchet_sl_80 < current_price * 0.999:
                best_sl = ratchet_sl_80
                active_stage = 'STAGE_RATCHET_80_OPEN'
                reasons.append(f"Ratchet80%(Open ${open_day:.2f}->High ${highest_seen:.2f}=>${ratchet_sl_80:.2f})")

        # ── A. Regla 2c: Si Precio > BB_Upper (en 5m o 15m), mover TSL a (Open - Delta) ──
        if df_5m is not None and len(df_5m) >= 6:
            c5 = _safe_col(df_5m, 'close')
            o5 = _safe_col(df_5m, 'open')
            bb_up_5 = float((c5.rolling(20, min_periods=5).mean() + 2.0 * c5.rolling(20, min_periods=5).std().fillna(0)).iloc[-1])
            open_5_now = float(o5.iloc[-1])
            if bb_up_5 > 0 and current_price > bb_up_5:
                cand_2c = round(open_5_now - delta, 2)
                if cand_2c > best_sl and cand_2c < current_price * 0.998:
                    best_sl = cand_2c
                    active_stage = 'STAGE_2C_OPEN_MINUS_DELTA'
                    reasons.append(f"2c(Open5m ${open_5_now:.2f}-Δ=${cand_2c:.2f})")

        # ── B. Regla B.5: Pasadas 3 velas de 5 minutos (age_mins >= 15.0) ──
        if age_mins >= 15.0:
            # Etapa 1: Precio OPEN de la vela de 5m superior al precio de compra
            if df_5m is not None and len(df_5m) >= 3:
                o5 = _safe_col(df_5m, 'open')
                # Buscar entre las últimas 6 velas de 5m aquellas cuyo OPEN > entry_p y < current_price
                recent_opens = [float(x) for x in o5.iloc[-6:].values if entry_p < float(x) < current_price * 0.997]
                if recent_opens:
                    cand_s1 = round(max(recent_opens), 2)
                    if cand_s1 > best_sl:
                        best_sl = cand_s1
                        active_stage = 'STAGE_1_OPEN5M_ABOVE_ENTRY'
                        reasons.append(f"Etapa1(Open5m>${entry_p:.2f} -> ${cand_s1:.2f})")

            # Etapa 2 y Etapa 3 en 15 minutos
            if df_15m is not None and len(df_15m) >= 9:
                c15 = _safe_col(df_15m, 'close')
                o15 = _safe_col(df_15m, 'open')
                ema3_15 = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
                ema9_15 = float(c15.ewm(span=9, adjust=False).mean().iloc[-1])
                bb_up_15 = float((c15.rolling(20, min_periods=5).mean() + 2.0 * c15.rolling(20, min_periods=5).std().fillna(0)).iloc[-1])
                open_15_now = float(o15.iloc[-1])

                # Etapa 2: (EMA9_15m - Delta) — solo se activa cuando asegura mínima ganancia (> entry_p)
                cand_s2 = round(ema9_15 - delta, 2)
                if cand_s2 > best_sl and cand_s2 > entry_p * 1.001 and cand_s2 < current_price * 0.997:
                    best_sl = cand_s2
                    active_stage = 'STAGE_2_EMA9_15M_MINUS_DELTA'
                    reasons.append(f"Etapa2(EMA9_15m ${ema9_15:.2f}-Δ=${cand_s2:.2f})")

                # Etapa 3: Si ((OPEN > BB_Upper) y (CLOSE > OPEN)) en 15m o 5m -> mover a (EMA3_15m - Delta)
                is_accel_15m = (bb_up_15 > 0 and open_15_now > bb_up_15 and current_price > open_15_now)
                is_accel_5m = False
                if df_5m is not None and len(df_5m) >= 6:
                    c5 = _safe_col(df_5m, 'close')
                    o5 = _safe_col(df_5m, 'open')
                    bb_up_5 = float((c5.rolling(20, min_periods=5).mean() + 2.0 * c5.rolling(20, min_periods=5).std().fillna(0)).iloc[-1])
                    open_5_now = float(o5.iloc[-1])
                    is_accel_5m = (bb_up_5 > 0 and open_5_now > bb_up_5 and current_price > open_5_now)

                if is_accel_15m or is_accel_5m:
                    cand_s3 = round(ema3_15 - delta, 2)
                    if cand_s3 > best_sl and cand_s3 > entry_p * 1.002 and cand_s3 < current_price * 0.997:
                        best_sl = cand_s3
                        active_stage = 'STAGE_3_EMA3_15M_MINUS_DELTA'
                        reasons.append(f"Etapa3(EMA3_15m ${ema3_15:.2f}-Δ=${cand_s3:.2f})")

        if best_sl > current_sl and best_sl < current_price:
            return {
                'should_update': True,
                'new_sl': best_sl,
                'stage': active_stage,
                'reason': f"TSL Escalonado [{active_stage}]: SL ${current_sl:.2f} -> ${best_sl:.2f} ({', '.join(reasons)})"
            }

        return {'should_update': False, 'new_sl': current_sl, 'stage': active_stage, 'reason': 'Sin cambio en TSL'}
    except Exception as e:
        log_warning(MODULE, f"Error en calculate_alpha_escalating_trailing_stop: {e}")
        return {'should_update': False, 'new_sl': current_sl, 'stage': 'ERROR', 'reason': str(e)}


def evaluate_aduana_stocks_exit(
    position: dict,
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    df_4h: Optional[pd.DataFrame] = None,
    df_1d: Optional[pd.DataFrame] = None,
    now_dt: Optional[datetime] = None,
) -> dict:
    """
    FUNCIÓN MAESTRA DEL MOTOR ADUANA DE SALIDAS PARA STOCKS (v6.0).
    Evalúa PnL, Motor Agudo Sección A (1a, 1b, 2a, 2b, 2c, 2d), Eje Estructural 15m (EMA3 vs EMA9),
    Maduración (>= +1.5%), Sub-Bandas Fibonacci en 3 Zonas, Micro-Gatillos 5m, Bollinger Macro y EOD Kinetic Trailing.
    """
    if not position or current_price <= 0:
        return {'should_close': False, 'action': 'HOLD', 'reason': 'Sin posición o precio inválido'}

    side = str(position.get('side', 'long')).lower()
    is_long = side in ('long', 'buy')
    entry_p = float(position.get('avg_price') or position.get('entry_price') or 0.0)
    shares = int(float(position.get('shares_remaining') or position.get('shares') or 0))

    if entry_p <= 0 or shares <= 0:
        return {'should_close': False, 'action': 'HOLD', 'reason': 'Entrada o acciones inválidas'}

    gain_pct = ((current_price - entry_p) / entry_p * 100.0) if is_long else ((entry_p - current_price) / entry_p * 100.0)
    pnl_usd = (current_price - entry_p) * shares if is_long else (entry_p - current_price) * shares

    # Calcular antigüedad real de la posición en minutos (compatible con simulación y tiempo real)
    entry_time_str = position.get('first_buy_at') or position.get('entry_time')
    age_mins = 0.0
    if entry_time_str:
        try:
            entry_dt = datetime.fromisoformat(str(entry_time_str).replace('Z', '+00:00'))
            ref_now = now_dt if now_dt is not None else datetime.now(timezone.utc)
            if getattr(ref_now, 'tzinfo', None) is not None and getattr(entry_dt, 'tzinfo', None) is not None:
                age_mins = (ref_now - entry_dt).total_seconds() / 60.0
            else:
                age_mins = (ref_now.replace(tzinfo=None) - entry_dt.replace(tzinfo=None)).total_seconds() / 60.0
        except Exception:
            age_mins = 0.0

    # ── 0. CIERRE FORZOSO EOD INCONDICIONAL (15:50 ET - CERO OVERNIGHT) ──
    if is_eod_hard_deadline(now_dt):
        return {
            'should_close': True,
            'action': 'CLOSE_TOTAL',
            'shares_to_close': shares,
            'pct_to_close': 100,
            'rule_code': 'ADUANA_STK_EOD_HARD_EXIT',
            'gain_pct': round(gain_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'reason': f"Hard-Exit EOD (15:50 ET): Liquidación forzosa incondicional del 100% para erradicar riesgo nocturno/dilución ({gain_pct:+.2f}% / ${pnl_usd:+.2f} USD)."
        }

    # ── 0.02 PROTOCOLO GOLDEN HOUR EOD (15:00 a 15:50 ET) PARA GANANCIA >= +5.0% ──
    try:
        from datetime import time as dt_time
        from zoneinfo import ZoneInfo
        ref_dt = now_dt or datetime.now(timezone.utc)
        ny_dt = ref_dt.astimezone(ZoneInfo('America/New_York')) if getattr(ref_dt, 'tzinfo', None) else ref_dt
        cur_t = ny_dt.time() if hasattr(ny_dt, 'time') else None
        is_wkday = getattr(ny_dt, 'weekday', lambda: 0)() < 5 if callable(getattr(ny_dt, 'weekday', None)) else True

        if is_wkday and cur_t is not None and gain_pct >= 5.0 and dt_time(15, 0) <= cur_t < dt_time(15, 50):
            gh_tp_done = bool(position.get("golden_hour_tp_executed") or position.get("tp_block1_executed"))
            # Fase 1: 15:00 a 15:30 ET -> Toma parcial 50%
            if dt_time(15, 0) <= cur_t < dt_time(15, 30) and not gh_tp_done:
                shares_50 = max(1, int(shares * 0.50))
                return {
                    'should_close': True,
                    'action': 'CLOSE_PARTIAL_50',
                    'shares_to_close': shares_50,
                    'pct_to_close': 50,
                    'rule_code': 'ADUANA_STK_GOLDEN_HOUR_TP50',
                    'gain_pct': round(gain_pct, 2),
                    'pnl_usd': round(pnl_usd, 2),
                    'reason': f"Golden Hour Fase 1 (15:00-15:30 ET): Venta parcial 50% asegurando +{gain_pct:.2f}% (>= +5.0%). Remanente con trailing ceñido."
                }
            # Fase 2: 15:30 a 15:50 ET -> Debilidad en 5m
            elif dt_time(15, 30) <= cur_t < dt_time(15, 50):
                is_weak = False
                weak_msg = ""
                if df_5m is not None and len(df_5m) >= 3:
                    c5 = _safe_col(df_5m, 'close')
                    if len(c5) >= 3:
                        e3_5 = c5.ewm(span=3, adjust=False).mean()
                        cur_e3 = float(e3_5.iloc[-1])
                        prev_e3 = float(e3_5.iloc[-2])
                        c_last = float(c5.iloc[-1])
                        if cur_e3 <= prev_e3:
                            is_weak = True
                            weak_msg = f"EMA3(5m) descendente/plana (${cur_e3:.2f} <= ${prev_e3:.2f})"
                        elif c_last < cur_e3:
                            is_weak = True
                            weak_msg = f"Close(5m) ${c_last:.2f} < EMA3 ${cur_e3:.2f}"
                if is_weak:
                    return {
                        'should_close': True,
                        'action': 'CLOSE_TOTAL',
                        'shares_to_close': shares,
                        'pct_to_close': 100,
                        'rule_code': 'ADUANA_STK_GOLDEN_HOUR_WEAKNESS',
                        'gain_pct': round(gain_pct, 2),
                        'pnl_usd': round(pnl_usd, 2),
                        'reason': f"Golden Hour Fase 2 (15:30-15:50 ET): {weak_msg} con profit +{gain_pct:.2f}%. Liquidando remanente."
                    }
    except Exception as e_gh:
        log_warning(MODULE, f"Error en Golden Hour EOD evaluation: {e_gh}")

    # ── 0.05 EVALUACIÓN PRIORITARIA FAST-TRACK IPO SUPER-RUNNER & ALPHA RUNNERS ──
    group_name = str(position.get('group_name', '') or position.get('pool_type', '')).upper()
    rule_pos = str(position.get('rule_code', '') or position.get('strategy', '')).upper()
    is_ft_eligible = ('FAST_TRACK' in group_name) or ('IPO_SUPER_RUNNER' in group_name) or ('ALPHA' in group_name) or ('FT_' in rule_pos) or ('FAST' in rule_pos) or ('IPO' in rule_pos) or (df_1d is not None and len(df_1d) <= 15)

    if is_ft_eligible:
        try:
            from app.stocks.fast_track_runner_engine import evaluate_fast_track_exits
            ft_res = evaluate_fast_track_exits(
                position=position,
                df_5m=df_5m,
                df_15m=df_15m,
                df_1h=df_1h,
                current_price=current_price
            )
            if ft_res.get('should_exit'):
                pct = ft_res.get('pct_to_sell', 100)
                action_str = 'CLOSE_TOTAL' if pct >= 100 else f"CLOSE_PARTIAL_{pct}"
                return {
                    'should_close': True,
                    'action': action_str,
                    'shares_to_close': ft_res.get('shares_to_sell', shares),
                    'pct_to_close': pct,
                    'rule_code': ft_res.get('rule_code', 'FT_PARTIAL_SELL'),
                    'gain_pct': round(gain_pct, 2),
                    'pnl_usd': round(pnl_usd, 2),
                    'reason': ft_res.get('reason', 'Fast-Track Exit'),
                    'should_update_sl': ft_res.get('should_update_sl', False),
                    'new_stop_loss': ft_res.get('new_stop_loss', 0.0),
                    'sl_reason': ft_res.get('sl_reason', '')
                }
        except Exception as e_ft:
            log_warning(MODULE, f"Error en evaluate_fast_track_exits: {e_ft}")

    # ── 0.1 CIERRE POR ESTANCAMIENTO / ZOMBIE TRADE (age_mins >= 45m sin tracción) ──
    # Evita que posiciones laterales terminen en ADUANA_STK_EOD_HARD_EXIT o STOP_LOSS_INITIAL
    if age_mins >= 45.0 and -0.45 <= gain_pct <= 0.25 and df_15m is not None and len(df_15m) >= 9 and df_5m is not None and len(df_5m) >= 3:
        try:
            c15 = _safe_col(df_15m, 'close')
            ema3_15 = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
            ema9_15 = float(c15.ewm(span=9, adjust=False).mean().iloc[-1])
            c5_now = float(_safe_col(df_5m, 'close').iloc[-1])
            o5_now = float(_safe_col(df_5m, 'open').iloc[-1])
            if ema3_15 <= ema9_15 * 1.0005 and c5_now <= o5_now:
                return {
                    'should_close': True,
                    'action': 'CLOSE_TOTAL',
                    'shares_to_close': shares,
                    'pct_to_close': 100,
                    'rule_code': 'ADUANA_ZOMBIE_TIME_EXIT',
                    'gain_pct': round(gain_pct, 2),
                    'pnl_usd': round(pnl_usd, 2),
                    'reason': f"Cierre por Estancamiento ({age_mins:.0f}m en posición, {gain_pct:+.2f}%): EMA3_15m <= EMA9_15m sin tracción alcista. Libera slot y evita EOD_HARD_EXIT."
                }
        except Exception:
            pass

    # ── CASO A: SI LA POSICIÓN ESTÁ EN PÉRDIDA O BREAKEVEN (gain_pct <= 0) ──
    if gain_pct <= 0:
        # ── BUFFER DE COST BASIS & ANTI-CHOPPING (Propuesta #2) ──
        # Si la pérdida no supera el -2.50%, la posición está dentro del colchón de oscilación inicial.
        # Se prohíben salidas por micro-ruido para no quedar atrapados por el spread Bid/Ask.
        if gain_pct > -2.50:
            return {
                'should_close': False,
                'action': 'HOLD',
                'gain_pct': round(gain_pct, 2),
                'pnl_usd': round(pnl_usd, 2),
                'reason': f"Cost Basis Buffer activo ({gain_pct:+.2f}%): Dentro del colchón de costo (-2.5% a 0%). Manejo delegado a Stop Loss Estructural formal."
            }

        # 0.2 ESCUDO DE INVALIDACIÓN ESTRUCTURAL 1H (Corte temprano si supera el buffer -2.50%)
        if age_mins >= 15.0 and gain_pct <= -2.50 and df_5m is not None and len(df_5m) >= 6 and df_15m is not None and len(df_15m) >= 9:
            try:
                c5 = _safe_col(df_5m, 'close')
                o5 = _safe_col(df_5m, 'open')
                v5 = _safe_col(df_5m, 'volume')
                ema3_5 = float(c5.ewm(span=3, adjust=False).mean().iloc[-1])
                ema9_5 = float(c5.ewm(span=9, adjust=False).mean().iloc[-1])
                c15 = _safe_col(df_15m, 'close')
                ema3_15 = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
                ema9_15 = float(c15.ewm(span=9, adjust=False).mean().iloc[-1])

                broke_1h_ema20 = False
                if df_1h is not None and len(df_1h) >= 6:
                    c1h = _safe_col(df_1h, 'close')
                    ema20_1h = float(c1h.ewm(span=20, adjust=False).mean().iloc[-1])
                    if ema20_1h > 0 and current_price < ema20_1h * 0.995:
                        broke_1h_ema20 = True

                # Confirmación de volumen vendedor real (Volume_5m >= SMA_Volume_10_5m * 0.90)
                mean_v5 = float(v5.iloc[-10:-1].mean()) if len(v5) >= 10 else 0.0
                curr_v5 = float(v5.iloc[-1]) if len(v5) >= 1 else 0.0
                has_selling_volume = (mean_v5 <= 0) or (curr_v5 >= mean_v5 * 0.90)

                if (broke_1h_ema20 or ema3_15 < ema9_15 * 0.994) and float(c5.iloc[-1]) < float(o5.iloc[-1]) and ema3_5 < ema9_5 and has_selling_volume:
                    return {
                        'should_close': True,
                        'action': 'CLOSE_TOTAL',
                        'shares_to_close': shares,
                        'pct_to_close': 100,
                        'rule_code': 'ADUANA_STRUCTURAL_1H_BREAK_EXIT',
                        'gain_pct': round(gain_pct, 2),
                        'pnl_usd': round(pnl_usd, 2),
                        'reason': f"Corte Temprano por Invalidación Estructural ({gain_pct:+.2f}%): Pérdida de EMA20_1H / EMA9_15m con volumen vendedor tras {age_mins:.0f}m. Evita recorrido hasta STOP_LOSS_INITIAL."
                    }
            except Exception:
                pass

        return {
            'should_close': False,
            'action': 'HOLD',
            'gain_pct': round(gain_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'reason': f"Posición sin ganancia ({gain_pct:.2f}%). Manejo delegado al Stop Loss Estructural."
        }

    # ── CASO B: POSICIÓN EN GANANCIA (gain_pct > 0) ──
    # ── 0.4 TAKE PROFIT ESTRUCTURAL POR PROXIMIDAD A MURO (<= 0.8% - SALIDA MARKET INMEDIATA) ──
    ticker_sym = str(position.get('ticker') or position.get('symbol') or '').upper().strip()
    if gain_pct >= 2.0 and ticker_sym and current_price > 0:
        try:
            from app.core.structural_regime_engine import evaluate_structural_regime
            st_reg = evaluate_structural_regime(ticker_sym, current_price, df_1d=df_1d)
            target_wall = float(st_reg.get("target_resistance_wall") or 0.0)
            target_ceiling = float(st_reg.get("target_ceiling") or 0.0)
            target_floor = float(st_reg.get("key_levels_1d", {}).get("bb_lower") or 0.0)

            if is_long:
                relevant_target = target_wall if (target_wall > current_price and target_wall < target_ceiling) else target_ceiling
                if relevant_target > 0:
                    dist_to_wall_pct = ((relevant_target - current_price) / current_price) * 100.0
                    if dist_to_wall_pct <= 0.80:
                        return {
                            'should_close': True,
                            'action': 'CLOSE_TOTAL',
                            'shares_to_close': shares,
                            'pct_to_close': 100,
                            'rule_code': 'ADUANA_STK_STRUCTURAL_TARGET_NEAR_TP',
                            'gain_pct': round(gain_pct, 2),
                            'pnl_usd': round(pnl_usd, 2),
                            'reason': f"Take Profit Estructural (Proximidad {dist_to_wall_pct:.2f}% <= 0.8%): Subyacente ${current_price:.2f} a las puertas de muro institucional ${relevant_target:.2f}. Salida MARKET inmediata para evitar front-running (+{gain_pct:.2f}%)."
                        }
            else:
                if target_floor > 0:
                    dist_to_floor_pct = ((current_price - target_floor) / current_price) * 100.0
                    if dist_to_floor_pct <= 0.80:
                        return {
                            'should_close': True,
                            'action': 'CLOSE_TOTAL',
                            'shares_to_close': shares,
                            'pct_to_close': 100,
                            'rule_code': 'ADUANA_STK_STRUCTURAL_TARGET_NEAR_TP',
                            'gain_pct': round(gain_pct, 2),
                            'pnl_usd': round(pnl_usd, 2),
                            'reason': f"Take Profit Estructural Short (Proximidad {dist_to_floor_pct:.2f}% <= 0.8%): Subyacente ${current_price:.2f} rozando soporte institucional ${target_floor:.2f}. Salida MARKET inmediata (+{gain_pct:.2f}%)."
                        }
        except Exception:
            pass

    # 0.5 EVALUACIÓN DEL MOTOR AGUDO SECCIÓN A (1a, 1b, 2a, 2b, 2c, 2d)
    sharp_res = evaluate_alpha_runner_sharp_exit(
        position=position,
        current_price=current_price,
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h
    )
    if sharp_res.get('should_close'):
        return {
            'should_close': True,
            'action': sharp_res['action'],
            'shares_to_close': sharp_res.get('shares_to_close', shares),
            'pct_to_close': sharp_res.get('pct_to_close', 100),
            'rule_code': sharp_res.get('rule_code', 'ALPHA_SHARP_EXIT'),
            'gain_pct': round(gain_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'reason': sharp_res.get('reason', 'Cierre Agudo Sección A'),
            'suggested_tsl_2c': sharp_res.get('suggested_tsl_2c', 0.0),
        }

    # 1. Bandas de Fibonacci en 15m y Sub-Bandas (Zonas 1, 2, 3)
    fib_15m = calculate_fibonacci_bands(df_15m, current_price)
    sub_bands = calculate_fibonacci_sub_bands(current_price, fib_15m, side)
    zone = sub_bands.get('zone', 1)

    # 2. Eje Estructural 15m (EMA3 vs EMA9 & Pendiente)
    ema_15m = evaluate_15m_ema_structure(df_15m, side)

    # 3. Micro-Gatillo táctico en 5m
    micro_5m = evaluate_5m_micro_trigger(df_5m, current_price, side)

    # 4. Macro Bollinger (1H, 4H, 1D)
    macro_bb = evaluate_macro_bollinger_levels(current_price, df_1h, df_4h, df_1d, side)

    # 5. Combustible en 15m
    fuel = evaluate_fuel_15m(df_15m, side)

    # ── NUEVA DOBLE VALIDACIÓN ADUANA EMA3 + BB (1H / 4H) ──
    from app.rebote_aduana.aduana_trend_exit import evaluate_aduana_trend_exit
    if df_1h is not None and len(df_1h) >= 2:
        trend_exit_res = evaluate_aduana_trend_exit(
            pos=position,
            current_price=current_price,
            df_1h=df_1h,
            df_4h=df_4h,
            min_profit_pct=0.5
        )
        act = trend_exit_res.get('action')
        if act in ('FULL_CLOSE', 'PARTIAL_CLOSE_50'):
            pct = 100 if act == 'FULL_CLOSE' else 50
            shares_to_sell = shares if pct == 100 else max(1, int(shares * 0.5))
            return {
                'should_close': True,
                'action': 'CLOSE_TOTAL' if pct == 100 else 'CLOSE_PARTIAL_50',
                'shares_to_close': shares_to_sell,
                'pct_to_close': pct,
                'rule_code': f"ADUANA_STK_{act}",
                'gain_pct': round(gain_pct, 2),
                'pnl_usd': round(pnl_usd, 2),
                'reason': f"ADUANA EMA3+BB Exit: {trend_exit_res.get('reason')}"
            }

    # Calcular antigüedad de la posición (evitar ahogar rebotes recién comprados en soporte)
    entry_time_str = position.get('first_buy_at') or position.get('entry_time')
    age_mins = 999.0
    if entry_time_str:
        try:
            entry_dt = datetime.fromisoformat(str(entry_time_str).replace('Z', '+00:00'))
            age_mins = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 60.0
        except Exception:
            pass

    # ── NUEVA REGLA: RATCHET 80% DEL AVANCE DESDE EL OPEN ──
    open_day_val = float(position.get('candle_open_day') or 0.0)
    if open_day_val <= 0 and df_5m is not None and len(df_5m) > 0:
        open_day_val = float(_safe_col(df_5m, 'open').iloc[0])
    if open_day_val <= 0:
        open_day_val = entry_p

    highest_peak = float(position.get('highest_price_reached') or position.get('trail_high') or current_price)
    if df_5m is not None and len(df_5m) > 0:
        h5_series = _safe_col(df_5m, 'high')
        if len(h5_series) > 0:
            highest_peak = max(highest_peak, float(h5_series.max()))

    if is_long and open_day_val > 0 and highest_peak >= (open_day_val * 1.08):
        ratchet_80_price = round(open_day_val + 0.80 * (highest_peak - open_day_val), 2)
        if current_price < ratchet_80_price and gain_pct >= 1.0:
            return {
                'should_close': True,
                'action': 'CLOSE_TOTAL',
                'shares_to_close': shares,
                'pct_to_close': 100,
                'rule_code': 'ADUANA_STK_RATCHET_80_OPEN_BREAK',
                'gain_pct': round(gain_pct, 2),
                'pnl_usd': round(pnl_usd, 2),
                'reason': f"Ratchet 80% Avance OPEN: High ${highest_peak:.2f} sobre Open ${open_day_val:.2f}. Protegiendo 80% del recorrido en ${ratchet_80_price:.2f}."
            }

    # ── NUEVA REGLA DINÁMICA 15M: TOMA PARCIAL POR DECAIMIENTO DE RVOL ──
    partial_rvol_done = bool(position.get('rvol_15m_tp_done') or position.get('tp_block1_executed') or position.get('climax_tp50_done'))
    if not partial_rvol_done and age_mins >= 14.0 and gain_pct >= 2.0 and is_long:
        is_decaying = (fuel.get('state') in ('EXHAUSTED', 'CLIMAX_EXHAUSTION')) or (fuel.get('rvol', 1.0) < 1.3)
        if is_decaying and micro_5m.get('is_trigger', False):
            shares_to_sell = max(1, int(shares * 0.5)) if shares > 1 else shares
            return {
                'should_close': True,
                'action': 'CLOSE_PARTIAL_50' if shares > 1 else 'CLOSE_TOTAL',
                'shares_to_close': shares_to_sell,
                'pct_to_close': 50 if shares > 1 else 100,
                'rule_code': 'ADUANA_STK_RVOL_15M_DECAY_TP50',
                'gain_pct': round(gain_pct, 2),
                'pnl_usd': round(pnl_usd, 2),
                'reason': f"TP Parcial Dinámico 15m: RVOL desacelerando ({fuel.get('reason')}). Asegurando 50% de ganancia (+{gain_pct:.2f}%)."
            }

    # ── 1. TOPE EOD INTRADÍA (15:15 - 15:50 ET) — ÚLTIMAS 3 VELAS DE 15m ──
    if is_eod_final_candles(now_dt):
        # Si la estructura de 15m se agotó o quebró Y tiene ganancia real (>= 1.2%) y maduración (>= 20 min):
        # No ahogar posiciones recién abiertas en LOWER_5 / LOWER_6 con ganancia de $0.00
        if (ema_15m.get('is_exhausted') or (not ema_15m.get('is_trend_alive'))) and gain_pct >= 1.2 and age_mins >= 20.0:
            return {
                'should_close': True,
                'action': 'CLOSE_TOTAL',
                'shares_to_close': shares,
                'pct_to_close': 100,
                'rule_code': 'ADUANA_STK_EOD_15M_BREAK',
                'gain_pct': round(gain_pct, 2),
                'pnl_usd': round(pnl_usd, 2),
                'reason': f"Tope EOD (últimas 3 velas 15:15-15:50 ET): Quiebre estructural en 15m ({ema_15m.get('reason')}). Cierre inmediato para asegurar ganancia (+{gain_pct:.2f}% / ${pnl_usd:.2f} USD)."
            }

        # Si la tendencia de 15m sigue viva: Cabalgar con Trailing Stop Estricto de Cierre
        highest_p = float(position.get('highest_price_reached') or current_price)
        peak_gain_pct = ((highest_p - entry_p) / entry_p * 100.0) if is_long else ((entry_p - highest_p) / entry_p * 100.0)

        # a) Piso inamovible: Al menos 70% de la ganancia máxima alcanzada
        if peak_gain_pct >= 0.5 and gain_pct < (peak_gain_pct * 0.70):
            return {
                'should_close': True,
                'action': 'CLOSE_TOTAL',
                'shares_to_close': shares,
                'pct_to_close': 100,
                'rule_code': 'ADUANA_STK_EOD_TRAILING_FLOOR_BREAK',
                'gain_pct': round(gain_pct, 2),
                'pnl_usd': round(pnl_usd, 2),
                'reason': f"Tope EOD Trailing: Perforó piso de 70% de ganancia máxima (+{peak_gain_pct:.2f}% -> +{gain_pct:.2f}%). Cierre protector."
            }

        # b) Trailing vela a vela en 5m (solo si ya hay ganancia real >= 1.0% y maduración >= 20 min)
        if df_5m is not None and len(df_5m) >= 2 and gain_pct >= 1.0 and age_mins >= 20.0:
            closes = _safe_col(df_5m, 'close')
            ema3_5m = closes.ewm(span=3, adjust=False).mean()
            cur_close = float(closes.iloc[-1])
            ema3_val = float(ema3_5m.iloc[-1])

            if is_long:
                lows = _safe_col(df_5m, 'low')
                prev_low = float(lows.iloc[-2])
                if current_price < prev_low or cur_close < ema3_val:
                    return {
                        'should_close': True,
                        'action': 'CLOSE_TOTAL',
                        'shares_to_close': shares,
                        'pct_to_close': 100,
                        'rule_code': 'ADUANA_STK_EOD_TRAILING_TRIGGER',
                        'gain_pct': round(gain_pct, 2),
                        'pnl_usd': round(pnl_usd, 2),
                        'reason': f"Tope EOD Trailing 5m: Perforación de Low previo (${prev_low:.2f}) o EMA3 5m (${ema3_val:.2f}). Cierre asegurando +{gain_pct:.2f}%."
                    }
            else:
                highs = _safe_col(df_5m, 'high')
                prev_high = float(highs.iloc[-2])
                if current_price > prev_high or cur_close > ema3_val:
                    return {
                        'should_close': True,
                        'action': 'CLOSE_TOTAL',
                        'shares_to_close': shares,
                        'pct_to_close': 100,
                        'rule_code': 'ADUANA_STK_EOD_TRAILING_TRIGGER',
                        'gain_pct': round(gain_pct, 2),
                        'pnl_usd': round(pnl_usd, 2),
                        'reason': f"Tope EOD Trailing 5m SHORT: Perforación de High previo (${prev_high:.2f}) o EMA3 5m (${ema3_val:.2f}). Cierre asegurando +{gain_pct:.2f}%."
                    }

        return {
            'should_close': False,
            'action': 'HOLD',
            'gain_pct': round(gain_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'reason': f"EOD Trailing Activo: Cabalgando últimas 3 velas con tendencia 15m viva ({ema_15m.get('reason')}). Piso 70% protegido."
        }

    # ── 2. TRAILING STOP ACELERADO EN ZONA 3 CLÍMAX (UPPER_5 / UPPER_6 / LOWER_5 / LOWER_6) ──
    if sub_bands['in_extreme_zone']:
        trailing_res = evaluate_accelerated_trailing_stop(position, current_price, df_5m, fib_15m, side)
        if trailing_res['action'] == 'TAKE_PROFIT_50_CLIMAX':
            shares_to_sell = max(1, int(shares * 0.5))
            return {
                'should_close': True,
                'action': 'CLOSE_PARTIAL_50',
                'shares_to_close': shares_to_sell,
                'pct_to_close': 50,
                'rule_code': trailing_res['rule_code'],
                'gain_pct': round(gain_pct, 2),
                'pnl_usd': round(pnl_usd, 2),
                'reason': trailing_res['reason']
            }
        elif trailing_res['action'] in ('CLOSE_TRAILING_LOW_BREAK', 'CLOSE_TRAILING_HIGH_BREAK', 'CLOSE_TRAILING_EMA3_BREAK'):
            return {
                'should_close': True,
                'action': 'CLOSE_TOTAL',
                'shares_to_close': shares,
                'pct_to_close': 100,
                'rule_code': trailing_res['rule_code'],
                'gain_pct': round(gain_pct, 2),
                'pnl_usd': round(pnl_usd, 2),
                'reason': trailing_res['reason']
            }

    # ── 3. SALIDAS POR TECHO MACRO BOLLINGER (1D / 4H / 1H) ──
    if macro_bb['hit_1d'] and micro_5m['is_trigger']:
        return {
            'should_close': True,
            'action': 'CLOSE_TOTAL',
            'shares_to_close': shares,
            'pct_to_close': 100,
            'rule_code': 'ADUANA_STK_MACRO_1D_TOTAL',
            'gain_pct': round(gain_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'reason': f"Techo Institucional Diario (1D) alcanzado (${macro_bb['bb_1d_upper']:.2f}) con giro en 5m. Cierre Total."
        }

    if macro_bb['hit_4h'] and micro_5m['is_trigger']:
        shares_to_sell = max(1, int(shares * 0.75)) if shares > 1 else shares
        return {
            'should_close': True,
            'action': 'CLOSE_MAJOR_75' if shares > 1 else 'CLOSE_TOTAL',
            'shares_to_close': shares_to_sell,
            'pct_to_close': 75 if shares > 1 else 100,
            'rule_code': 'ADUANA_STK_MACRO_4H_TP',
            'gain_pct': round(gain_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'reason': f"Techo Mayor de 4H alcanzado (${macro_bb['bb_4h_upper']:.2f}) con giro en 5m. Cierre del 75% asegurado."
        }

    partial_1h_done = bool(position.get('tp_1h_executed') or position.get('tp_block1_executed'))
    if macro_bb['hit_1h'] and micro_5m['is_trigger'] and not partial_1h_done and shares >= 2:
        shares_to_sell = max(1, int(shares * 0.5))
        return {
            'should_close': True,
            'action': 'CLOSE_PARTIAL_50',
            'shares_to_close': shares_to_sell,
            'pct_to_close': 50,
            'rule_code': 'ADUANA_STK_MACRO_1H_TP50',
            'gain_pct': round(gain_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'reason': f"Techo de 1H alcanzado (${macro_bb['bb_1h_upper']:.2f}) con agotamiento en 5m. Cierre parcial del 50%."
        }

    # ── 4. REGLA DE ORO DE MADURACIÓN (< +1.5%) ──
    # Mientras la ganancia actual sea MENOR a +1.5% y la tendencia estructural de 15m esté VIVA
    # (EMA3 > EMA9 en LONG / EMA3 < EMA9 en SHORT):
    # SE PROHÍBE cualquier cierre por micro-ruido de 5m o falsos agotamientos.
    if gain_pct < 1.5 and ema_15m.get('is_trend_alive'):
        be_status = "Piso Breakeven ($0.00) asegurado" if gain_pct >= 0.5 else "Espacio de arranque inicial"
        return {
            'should_close': False,
            'action': 'HOLD',
            'gain_pct': round(gain_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'reason': (
                f"Fase de Maduración (<+1.5%, actual +{gain_pct:.2f}% en Zona {zone}): "
                f"Tendencia 15m viva ({ema_15m.get('reason')}). {be_status}. "
                f"Guardando espacio y bloqueando salidas de 5m."
            )
        }

    # ── 5. REGLA MAESTRA DE GUARDAR ESPACIO POR COMBUSTIBLE ALTO EN 15M ──
    if fuel['state'] == 'HIGH_FUEL' and not macro_bb['hit_1d'] and not sub_bands.get('is_upper6', False) and not sub_bands.get('is_lower6', False):
        return {
            'should_close': False,
            'action': 'HOLD',
            'gain_pct': round(gain_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'reason': f"Guardando espacio: {fuel['reason']} (Impulso con inercia hacia {sub_bands['major_target']})."
        }

    # ── 6. SALIDA POR AGOTAMIENTO EN ZONA 2 / ZONA 3 (Maduración >= +1.5% o Tendencia 15m Agotada) ──
    # Si estamos en Sub-Banda 3 (tercio superior) O el combustible 15m se agotó/clímax O la EMA 15m se agotó,
    # Y los 5m confirman el cruce en contra o Bollinger horizontal:
    if (sub_bands['in_exhaustion_zone'] or ema_15m.get('is_exhausted') or fuel['state'] in ('EXHAUSTED', 'CLIMAX_EXHAUSTION') or macro_bb['bb_1h_flat']):
        if micro_5m['is_trigger']:
            return {
                'should_close': True,
                'action': 'CLOSE_TOTAL',
                'shares_to_close': shares,
                'pct_to_close': 100,
                'rule_code': 'ADUANA_STK_EXHAUSTION_EXIT',
                'gain_pct': round(gain_pct, 2),
                'pnl_usd': round(pnl_usd, 2),
                'reason': f"Salida por Agotamiento: En {sub_bands['interval']} (Sub-Banda {sub_bands['sub_band']}) + Combustible {fuel['state']} + Gatillo 5m ({micro_5m['reason']}). Ganancia asegurada: +{gain_pct:.2f}%."
            }

    # ── 7. PROTECCIÓN DE GANANCIA MÍNIMA (Micro-Trailing tras rally >= 2.0%) ──
    highest_p = float(position.get('highest_price_reached') or current_price)
    if entry_p > 0 and highest_p > entry_p:
        peak_gain_pct = (highest_p - entry_p) / entry_p * 100.0 if is_long else (entry_p - highest_p) / entry_p * 100.0
        if peak_gain_pct >= 2.0 and gain_pct <= (peak_gain_pct * 0.60) and micro_5m['is_trigger']:
            return {
                'should_close': True,
                'action': 'CLOSE_TOTAL',
                'shares_to_close': shares,
                'pct_to_close': 100,
                'rule_code': 'ADUANA_STK_PEAK_PULLBACK_PROTECTION',
                'gain_pct': round(gain_pct, 2),
                'pnl_usd': round(pnl_usd, 2),
                'reason': f"Micro-Trailing de Ganancia: Retroceso de 40% desde el pico (+{peak_gain_pct:.2f}% -> +{gain_pct:.2f}%) con quiebre de EMA 5m. Cierre protector."
            }

    return {
        'should_close': False,
        'action': 'HOLD',
        'gain_pct': round(gain_pct, 2),
        'pnl_usd': round(pnl_usd, 2),
        'reason': f"Impulso favorable ({sub_bands['interval']} Sub-{sub_bands['sub_band']}). Combustible {fuel['state']}. Mantener ganancia."
    }


def calculate_1h_trailing_stop(
    position: dict,
    current_price: float,
    df_1h: Optional[pd.DataFrame]
) -> dict:
    """
    Calcula el Trailing Stop Estructural en velas de 1 HORA.
    - Anclado al Low de la vela horaria previa (Low[t-1]) o EMA9 de 1H.
    - Preserva el Stop Loss de emergencia intacto si el trailing no lo supera.
    """
    side = str(position.get('side', 'long')).lower()
    is_long = side in ('long', 'buy')
    entry_p = float(position.get('avg_price') or position.get('entry_price') or 0.0)
    current_sl = float(position.get('stop_loss') or 0.0)

    if not is_long or df_1h is None or len(df_1h) < 2 or current_price <= 0:
        return {'should_update': False, 'new_sl': current_sl, 'reason': 'Condiciones no aplicables'}

    try:
        lows = _safe_col(df_1h, 'low')
        closes = _safe_col(df_1h, 'close')
        prev_low = float(lows.iloc[-2]) if len(lows) >= 2 else float(lows.iloc[-1])
        ema9 = float(closes.ewm(span=9, adjust=False).mean().iloc[-1])

        # Nivel propuesto: máximo entre prev_low * 0.998 y ema9 * 0.995
        proposed_sl = round(max(prev_low * 0.998, ema9 * 0.995), 2)

        # Solo sube si supera el SL actual sin superar el precio actual
        if proposed_sl > current_sl and proposed_sl < current_price:
            return {
                'should_update': True,
                'new_sl': proposed_sl,
                'prev_sl': current_sl,
                'prev_low_1h': prev_low,
                'ema9_1h': round(ema9, 2),
                'reason': f"Trailing 1H activado: Nuevo SL=${proposed_sl:.2f} (Low 1H previo=${prev_low:.2f}, EMA9_1H=${ema9:.2f}) > SL actual=${current_sl:.2f}"
            }

        return {
            'should_update': False,
            'new_sl': current_sl,
            'reason': f"SL actual (${current_sl:.2f}) ya es superior o propuesto (${proposed_sl:.2f}) no supera."
        }
    except Exception as e:
        return {'should_update': False, 'new_sl': current_sl, 'reason': f"Error: {e}"}

