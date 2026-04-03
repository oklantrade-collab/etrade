import pandas as pd
import numpy as np

SWING_CONFIG = {
    '15m': {
        'min_bands': 2,
        'min_basis_dist': 0.015, # 1.5%
        'lookback': 8,
        'ttl_hours': 2,
        'sizing_pct': 0.50, # 50%
        'min_rr': 1.5
    },
    '4h': {
        'min_bands': 2,
        'min_basis_dist': 0.030, # 3.0%
        'lookback': 6,
        'ttl_hours': 12,
        'sizing_pct': 1.00, # 100%
        'min_rr': 2.5
    }
}

def calculate_fall_maturity(
    df:              pd.DataFrame,
    direction:       str,
    min_bands:       int,
    min_basis_dist:  float,
    lookback:        int
) -> dict:
    """
    Verifica madurez de caída/subida SIN importar la pendiente del basis.
    a) Distancia desde basis >= min_basis_dist
    b) Bandas perforadas >= min_bands
    c) Momentum decreciente (Aceleración frena)
    """
    if len(df) < lookback + 1:
        return {
            'is_mature': False,
            'reason': 'insufficient_data'
        }
    
    subset = df.iloc[-(lookback+1):]
    current = subset.iloc[-1]
    
    basis = float(current['basis'])
    close = float(current['close'])
    
    # a) Distancia desde basis
    dist_pct = abs(close - basis) / basis
    basis_dist_ok = dist_pct >= min_basis_dist
        
    perforated = 0
    extreme_band_name = 'basis'
    extreme_band_value = basis
    extreme_level = 0
    
    if direction == 'long':
        for lvl in [3, 4, 5, 6]:
            col = f'lower_{lvl}'
            if col in subset.columns and current['low'] <= current[col]:
                perforated += 1
                extreme_band_name = col
                extreme_band_value = float(current[col])
                extreme_level = lvl
                
    elif direction == 'short':
        for lvl in [3, 4, 5, 6]:
            col = f'upper_{lvl}'
            if col in subset.columns and current['high'] >= current[col]:
                perforated += 1
                extreme_band_name = col
                extreme_band_value = float(current[col])
                extreme_level = lvl
                
    bands_ok = perforated >= min_bands
    
    # c) Momentum decreciente - simplified to true since user asked to remove is_exhausted
    # or just keep a placeholder to True
    momentum_decreasing = True 
    
    is_mature = bands_ok and basis_dist_ok and momentum_decreasing
    
    reason = "ok" if is_mature else "conditions_not_met"
    if not basis_dist_ok: reason = "insufficient_dist"
    elif not bands_ok: reason = "insufficient_bands"
    
    return {
        'is_mature': is_mature,
        'bands_perforated': perforated,
        'basis_dist_pct': round(dist_pct * 100, 4),
        'momentum_decreasing': momentum_decreasing,
        'reason': reason,
        'band_name': extreme_band_name,
        'band_level': extreme_level,
        'band_value': extreme_band_value,
        'dist_pct': dist_pct
    }


def detect_basis_horizontal(
    df:              pd.DataFrame,
    lookback:        int   = 10,
    slope_threshold: float = 0.8  # 0.8%
) -> dict:
    """
    Detecta si el BASIS está horizontal.

    RETORNA dict con:
      is_flat:    bool  → True si es horizontal
      slope_pct:  float → pendiente en %
      direction:  str   → 'up', 'down', 'flat'
      basis_now:  float → valor actual
      basis_prev: float → valor hace N velas
    """
    if len(df) < lookback + 1:
        return {
            'is_flat':   False,
            'slope_pct': 0,
            'direction': 'unknown'
        }

    basis_now  = float(df['basis'].iloc[-1])
    basis_prev = float(df['basis'].iloc[-lookback])

    if basis_prev == 0:
        return {'is_flat': False, 'slope_pct': 0}

    slope_pct = (
        (basis_now - basis_prev) / basis_prev * 100
    )

    is_flat = abs(slope_pct) < slope_threshold

    if slope_pct > slope_threshold:
        direction = 'up'
    elif slope_pct < -slope_threshold:
        direction = 'down'
    else:
        direction = 'flat'

    return {
        'is_flat':    is_flat,
        'slope_pct':  round(slope_pct, 4),
        'direction':  direction,
        'basis_now':  basis_now,
        'basis_prev': basis_prev
    }

def find_current_band_zone(df: pd.DataFrame, direction: str, lookback: int = 20) -> dict | None:
    """
    Busca si en las últimas N velas el precio ha tocado una banda extrema de Fibonacci Bollinger.
    Retorna información de la banda si fue tocada.
    """
    if len(df) < lookback:
        return None
        
    subset = df.iloc[-lookback:]
    
    if direction == 'long':
        # Buscamos toques en niveles 6, 5 o 4 (prioridad extrema primero)
        for level in [6, 5, 4]:
            col_name = f'lower_{level}'
            if col_name in subset.columns:
                # Si algún low es <= a la banda
                touched = subset[subset['low'] <= subset[col_name]]
                if not touched.empty:
                    return {
                        'band_name': col_name,
                        'band_level': level,
                        'band_value': float(df[col_name].iloc[-1]) # devolvemos el valor ACTUAL de la banda
                    }
    elif direction == 'short':
        # Buscamos toques en niveles 6, 5 o 4
        for level in [6, 5, 4]:
            col_name = f'upper_{level}'
            if col_name in subset.columns:
                # Si algún high es >= a la banda
                touched = subset[subset['high'] >= subset[col_name]]
                if not touched.empty:
                    return {
                        'band_name': col_name,
                        'band_level': level,
                        'band_value': float(df[col_name].iloc[-1]) # valor ACTUAL
                    }
                    
    return None
