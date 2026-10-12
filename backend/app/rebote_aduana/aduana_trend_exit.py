"""
ADUANA Trend Exit Monitor — Inflexión de EMA3 y Doble Validación con Bandas de Bollinger (1h / 4h)
Mercados: Crypto Futures (Binance) & Forex (IC Markets / cTrader)
Temporalidades: 1h y 4h
"""

import math
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from app.core.logger import log_info, log_warning, log_error

MODULE = "ADUANA_TREND_EXIT"

EPSILON_TOLERANCE = 0.02  # 0.02% para considerar pendiente plana / horizontal


def _extract_indicators_from_df(df: pd.DataFrame) -> Optional[dict]:
    """
    Extrae EMA3, EMA9, Upper Bollinger y Lower Bollinger para las 2 últimas velas cerradas.
    Calcula dinámicamente si alguna columna falta.
    """
    if df is None or len(df) < 2:
        return None

    c_col = 'close' if 'close' in df.columns else ('Close' if 'Close' in df.columns else None)
    if not c_col:
        return None

    close_series = pd.to_numeric(df[c_col], errors='coerce').dropna()
    if len(close_series) < 2:
        return None

    # EMA3
    if 'ema_3' in df.columns:
        ema3_s = pd.to_numeric(df['ema_3'], errors='coerce')
    elif 'ema1' in df.columns:
        ema3_s = pd.to_numeric(df['ema1'], errors='coerce')
    elif 'ema3' in df.columns:
        ema3_s = pd.to_numeric(df['ema3'], errors='coerce')
    else:
        ema3_s = close_series.ewm(span=3, adjust=False).mean()

    # EMA9
    if 'ema_9' in df.columns:
        ema9_s = pd.to_numeric(df['ema_9'], errors='coerce')
    elif 'ema2' in df.columns:
        ema9_s = pd.to_numeric(df['ema2'], errors='coerce')
    elif 'ema9' in df.columns:
        ema9_s = pd.to_numeric(df['ema9'], errors='coerce')
    else:
        ema9_s = close_series.ewm(span=9, adjust=False).mean()

    # Bollinger Bands (Upper y Lower)
    # 1. Chequeo de columnas existentes
    upper_col = None
    for cand in ['upper_2', 'upper', 'bb_upper', 'bb_upper_2']:
        if cand in df.columns:
            upper_col = cand
            break

    lower_col = None
    for cand in ['lower_2', 'lower', 'bb_lower', 'bb_lower_2']:
        if cand in df.columns:
            lower_col = cand
            break

    if upper_col and lower_col:
        upper_s = pd.to_numeric(df[upper_col], errors='coerce')
        lower_s = pd.to_numeric(df[lower_col], errors='coerce')
    else:
        # Calcular estándar 20, 2 std
        basis = close_series.rolling(min(len(close_series), 20)).mean()
        std = close_series.rolling(min(len(close_series), 20)).std().fillna(0)
        upper_s = basis + (2.0 * std)
        lower_s = basis - (2.0 * std)

    # Tomar las últimas dos velas
    ema3_curr = float(ema3_s.iloc[-1])
    ema3_prev = float(ema3_s.iloc[-2]) if len(ema3_s) >= 2 else ema3_curr

    ema9_curr = float(ema9_s.iloc[-1])
    ema9_prev = float(ema9_s.iloc[-2]) if len(ema9_s) >= 2 else ema9_curr

    upper_curr = float(upper_s.iloc[-1])
    upper_prev = float(upper_s.iloc[-2]) if len(upper_s) >= 2 else upper_curr

    lower_curr = float(lower_s.iloc[-1])
    lower_prev = float(lower_s.iloc[-2]) if len(lower_s) >= 2 else lower_curr

    # Pendientes porcentuales (%)
    slope_ema3 = ((ema3_curr - ema3_prev) / ema3_prev * 100.0) if ema3_prev > 0 else 0.0
    slope_upper = ((upper_curr - upper_prev) / upper_prev * 100.0) if upper_prev > 0 else 0.0
    slope_lower = ((lower_curr - lower_prev) / lower_prev * 100.0) if lower_prev > 0 else 0.0

    return {
        'ema3_curr': ema3_curr,
        'ema3_prev': ema3_prev,
        'slope_ema3': slope_ema3,
        'ema9_curr': ema9_curr,
        'ema9_prev': ema9_prev,
        'upper_curr': upper_curr,
        'upper_prev': upper_prev,
        'slope_upper': slope_upper,
        'lower_curr': lower_curr,
        'lower_prev': lower_prev,
        'slope_lower': slope_lower,
    }


def evaluate_aduana_trend_exit(
    pos: dict,
    current_price: float,
    df_1h: Optional[pd.DataFrame] = None,
    df_4h: Optional[pd.DataFrame] = None,
    min_profit_pct: float = 0.35,
    min_profit_pips: float = 4.0
) -> Dict[str, Any]:
    """
    Evalúa la salida de ADUANA por agotamiento tendencial con doble validación Bollinger.

    Returns:
        dict con:
        - action: 'FULL_CLOSE', 'PARTIAL_CLOSE_50', 'HOLD'
        - reason: Explicación humana
        - details: métricas de pendientes y bandas
    """
    side = (pos.get('side') or '').lower()
    is_long = side in ('long', 'buy')
    entry_p = float(pos.get('entry_price') or pos.get('avg_entry_price') or 0.0)

    if entry_p <= 0 or current_price <= 0:
        return {'action': 'HOLD', 'reason': 'Precio o entrada inválida.', 'details': {}}

    symbol = str(pos.get('symbol') or '').upper()
    is_forex = any(x in symbol for x in ('EUR', 'GBP', 'USD', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD', 'XAU')) and not any(x in symbol for x in ('USDT', 'BUSD', 'BTC'))
    
    # Cálculo de PnL
    if is_long:
        pnl_pct = (current_price - entry_p) / entry_p * 100.0
    else:
        pnl_pct = (entry_p - current_price) / entry_p * 100.0

    pip_size = 0.01 if ('JPY' in symbol or 'XAU' in symbol) else 0.0001
    pnl_pips = (current_price - entry_p) / pip_size if is_long else (entry_p - current_price) / pip_size

    # Guard de Ganancia Mínima:
    # Solo aplicamos salida inteligente si la posición está en ganancia razonable.
    # Si está en pérdida o apenas en BE, el Hard SL estructural es el responsable.
    in_profit = pnl_pips >= min_profit_pips if is_forex else pnl_pct >= min_profit_pct
    if not in_profit:
        return {
            'action': 'HOLD',
            'reason': f'Posición no supera umbral mínimo de ganancia para ADUANA exit (PnL={pnl_pct:.2f}%, Pips={pnl_pips:.1f}).',
            'details': {'pnl_pct': pnl_pct, 'pnl_pips': pnl_pips}
        }

    # Extraer indicadores de 1 hora
    ind_1h = _extract_indicators_from_df(df_1h)
    ind_4h = _extract_indicators_from_df(df_4h) if df_4h is not None else None

    if not ind_1h:
        return {'action': 'HOLD', 'reason': 'Datos 1h insuficientes para ADUANA.', 'details': {}}

    partial_already_taken = bool(pos.get('partial_closed', False))

    # ─────────────────────────────────────────────────────────────
    # CASO LONG
    # ─────────────────────────────────────────────────────────────
    if is_long:
        ema3_1h = ind_1h['ema3_curr']
        ema9_1h = ind_1h['ema9_curr']
        slope_ema3_1h = ind_1h['slope_ema3']
        slope_upper_1h = ind_1h['slope_upper']

        # 1. Cruce bajista en 1h: EMA3 cruza o está por debajo de EMA9
        if ema3_1h <= ema9_1h:
            return {
                'action': 'FULL_CLOSE',
                'reason': f'ADUANA LONG [1h]: Cruce bajista EMA3 ({ema3_1h:.5f}) <= EMA9 ({ema9_1h:.5f}). Cierre total.',
                'details': {
                    'pnl_pct': pnl_pct, 'timeframe': '1h',
                    'ema3': ema3_1h, 'ema9': ema9_1h,
                    'slope_ema3': slope_ema3_1h, 'slope_upper': slope_upper_1h
                }
            }

        # 2. Inflexión de EMA3 en 1h: Se vuelve horizontal o negativa mientras EMA3 > EMA9
        ema3_exhausted_1h = slope_ema3_1h <= EPSILON_TOLERANCE

        if ema3_exhausted_1h:
            # Doble Validación: Banda Superior de Bollinger 1h
            upper_exhausted_1h = slope_upper_1h <= EPSILON_TOLERANCE

            if upper_exhausted_1h:
                # Agotamiento total (ambos indicadores planos o negativos)
                return {
                    'action': 'FULL_CLOSE',
                    'reason': f'ADUANA LONG [1h]: Doble validación cumplida (Slope EMA3={slope_ema3_1h:.3f}% <= 0, Slope Upper BB={slope_upper_1h:.3f}% <= 0). Cierre 100%.',
                    'details': {
                        'pnl_pct': pnl_pct, 'timeframe': '1h',
                        'slope_ema3': slope_ema3_1h, 'slope_upper': slope_upper_1h
                    }
                }
            else:
                # Banda superior aún expande hacia arriba -> Cierre Parcial 50%
                if not partial_already_taken:
                    return {
                        'action': 'PARTIAL_CLOSE_50',
                        'reason': f'ADUANA LONG [1h]: EMA3 frenó ({slope_ema3_1h:.3f}%), pero Upper BB sigue expandiendo ({slope_upper_1h:.3f}%). Cierre parcial 50% + Trailing 1h.',
                        'details': {
                            'pnl_pct': pnl_pct, 'timeframe': '1h',
                            'slope_ema3': slope_ema3_1h, 'slope_upper': slope_upper_1h
                        }
                    }

        # 3. Supervisión de 4 Horas (si la posición sigue viva y tenemos datos de 4h)
        if ind_4h:
            ema3_4h = ind_4h['ema3_curr']
            ema9_4h = ind_4h['ema9_curr']
            slope_ema3_4h = ind_4h['slope_ema3']
            slope_upper_4h = ind_4h['slope_upper']

            if ema3_4h <= ema9_4h:
                return {
                    'action': 'FULL_CLOSE',
                    'reason': f'ADUANA LONG [4h]: Cruce bajista macro EMA3 ({ema3_4h:.5f}) <= EMA9 ({ema9_4h:.5f}). Cierre total.',
                    'details': {'pnl_pct': pnl_pct, 'timeframe': '4h', 'slope_ema3': slope_ema3_4h}
                }

            ema3_exhausted_4h = slope_ema3_4h <= EPSILON_TOLERANCE
            if ema3_exhausted_4h:
                upper_exhausted_4h = slope_upper_4h <= EPSILON_TOLERANCE
                if upper_exhausted_4h:
                    return {
                        'action': 'FULL_CLOSE',
                        'reason': f'ADUANA LONG [4h]: Agotamiento macro confirmado (Slope EMA3={slope_ema3_4h:.3f}% <= 0, Slope Upper BB={slope_upper_4h:.3f}% <= 0). Cierre total remanente.',
                        'details': {
                            'pnl_pct': pnl_pct, 'timeframe': '4h',
                            'slope_ema3': slope_ema3_4h, 'slope_upper': slope_upper_4h
                        }
                    }

        # Condición de espera: EMA3 > EMA9 y pendiente alcista -> HOLD
        return {
            'action': 'HOLD',
            'reason': f'ADUANA LONG: Tendencia activa (EMA3 > EMA9, Slope EMA3={slope_ema3_1h:.3f}% > 0). Esperar y dejar correr.',
            'details': {'pnl_pct': pnl_pct, 'slope_ema3': slope_ema3_1h}
        }

    # ─────────────────────────────────────────────────────────────
    # CASO SHORT
    # ─────────────────────────────────────────────────────────────
    else:
        ema3_1h = ind_1h['ema3_curr']
        ema9_1h = ind_1h['ema9_curr']
        slope_ema3_1h = ind_1h['slope_ema3']
        slope_lower_1h = ind_1h['slope_lower']

        # 1. Cruce alcista en 1h: EMA3 cruza o está por encima de EMA9
        if ema3_1h >= ema9_1h:
            return {
                'action': 'FULL_CLOSE',
                'reason': f'ADUANA SHORT [1h]: Cruce alcista EMA3 ({ema3_1h:.5f}) >= EMA9 ({ema9_1h:.5f}). Cierre total.',
                'details': {
                    'pnl_pct': pnl_pct, 'timeframe': '1h',
                    'ema3': ema3_1h, 'ema9': ema9_1h,
                    'slope_ema3': slope_ema3_1h, 'slope_lower': slope_lower_1h
                }
            }

        # 2. Inflexión de EMA3 en 1h: Se vuelve horizontal o positiva mientras EMA3 < EMA9
        ema3_exhausted_1h = slope_ema3_1h >= -EPSILON_TOLERANCE

        if ema3_exhausted_1h:
            # Doble Validación: Banda Inferior de Bollinger 1h
            # En caída, la banda inferior se abre hacia abajo (slope < 0).
            # Si frena o sube (slope >= -EPSILON), la expansión bajista terminó.
            lower_exhausted_1h = slope_lower_1h >= -EPSILON_TOLERANCE

            if lower_exhausted_1h:
                # Agotamiento total bajista
                return {
                    'action': 'FULL_CLOSE',
                    'reason': f'ADUANA SHORT [1h]: Doble validación cumplida (Slope EMA3={slope_ema3_1h:.3f}% >= 0, Slope Lower BB={slope_lower_1h:.3f}% >= 0). Cierre 100%.',
                    'details': {
                        'pnl_pct': pnl_pct, 'timeframe': '1h',
                        'slope_ema3': slope_ema3_1h, 'slope_lower': slope_lower_1h
                    }
                }
            else:
                # Banda inferior aún expande hacia abajo -> Cierre Parcial 50%
                if not partial_already_taken:
                    return {
                        'action': 'PARTIAL_CLOSE_50',
                        'reason': f'ADUANA SHORT [1h]: EMA3 frenó ({slope_ema3_1h:.3f}%), pero Lower BB sigue expandiendo ({slope_lower_1h:.3f}%). Cierre parcial 50% + Trailing 1h.',
                        'details': {
                            'pnl_pct': pnl_pct, 'timeframe': '1h',
                            'slope_ema3': slope_ema3_1h, 'slope_lower': slope_lower_1h
                        }
                    }

        # 3. Supervisión de 4 Horas
        if ind_4h:
            ema3_4h = ind_4h['ema3_curr']
            ema9_4h = ind_4h['ema9_curr']
            slope_ema3_4h = ind_4h['slope_ema3']
            slope_lower_4h = ind_4h['slope_lower']

            if ema3_4h >= ema9_4h:
                return {
                    'action': 'FULL_CLOSE',
                    'reason': f'ADUANA SHORT [4h]: Cruce alcista macro EMA3 ({ema3_4h:.5f}) >= EMA9 ({ema9_4h:.5f}). Cierre total.',
                    'details': {'pnl_pct': pnl_pct, 'timeframe': '4h', 'slope_ema3': slope_ema3_4h}
                }

            ema3_exhausted_4h = slope_ema3_4h >= -EPSILON_TOLERANCE
            if ema3_exhausted_4h:
                lower_exhausted_4h = slope_lower_4h >= -EPSILON_TOLERANCE
                if lower_exhausted_4h:
                    return {
                        'action': 'FULL_CLOSE',
                        'reason': f'ADUANA SHORT [4h]: Agotamiento macro confirmado (Slope EMA3={slope_ema3_4h:.3f}% >= 0, Slope Lower BB={slope_lower_4h:.3f}% >= 0). Cierre total remanente.',
                        'details': {
                            'pnl_pct': pnl_pct, 'timeframe': '4h',
                            'slope_ema3': slope_ema3_4h, 'slope_lower': slope_lower_4h
                        }
                    }

        # Condición de espera: EMA3 < EMA9 y pendiente bajista -> HOLD
        return {
            'action': 'HOLD',
            'reason': f'ADUANA SHORT: Tendencia bajista activa (EMA3 < EMA9, Slope EMA3={slope_ema3_1h:.3f}% < 0). Esperar y dejar correr.',
            'details': {'pnl_pct': pnl_pct, 'slope_ema3': slope_ema3_1h}
        }
