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
    Evalúa PnL, Eje Estructural 15m (EMA3 vs EMA9), Maduración (>= +1.5%),
    Sub-Bandas Fibonacci en 3 Zonas, Micro-Gatillos 5m, Bollinger Macro y EOD Kinetic Trailing.
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

    # ── 0. CIERRE FORZOSO EOD INCONDICIONAL (15:50 ET - CERO OVERNIGHT) ──
    # A las 15:50 ET o más tarde, se liquida el 100% incondicionalmente
    # sin importar si la posición está en ganancia o pérdida, erradicando el riesgo nocturno.
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

    # ── CASO A: SI LA POSICIÓN ESTÁ EN PÉRDIDA O BREAKEVEN (gain_pct <= 0) ──
    # El motor de TP/Salida con Ganancia no interfiere; la gestión de pérdida la maneja el SL / Panic Recovery Gate.
    if gain_pct <= 0:
        return {
            'should_close': False,
            'action': 'HOLD',
            'gain_pct': round(gain_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'reason': f"Posición sin ganancia ({gain_pct:.2f}%). Manejo delegado al Stop Loss Estructural."
        }

    # ── CASO B: POSICIÓN EN GANANCIA (gain_pct > 0) ──
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

