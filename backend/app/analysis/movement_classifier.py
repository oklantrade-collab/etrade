import pandas as pd
import numpy as np


def classify_movement(
    df:           pd.DataFrame,
    lookback:     int   = 20,
    basis_col:    str   = 'basis',
    ema200_col:   str   = 'ema_200',
    slope_strong: float = 0.003,  # 0.3% — realistic for 20 candles
    slope_weak:   float = 0.0005, # 0.05%
) -> dict:
    """
    Clasifica el movimiento actual del mercado
    usando BASIS slope, EMA200 slope y zona Fibonacci.

    Returns dict con:
      movement_type: str (7 tipos)
      basis_slope_pct: float
      ema200_slope_pct: float
      fib_zone_current: int
      confidence: float (0-1)
      signal_bias: str ('long_bias' | 'short_bias' | 'neutral')
      description: str
    """
    if df is None or len(df) < lookback + 1:
        return {
            'movement_type':   'irregular',
            'confidence':      0.0,
            'signal_bias':     'neutral',
            'description':     'Datos insuficientes',
            'basis_slope_pct': 0.0,
            'ema200_slope_pct': 0.0,
            'fib_zone_current': 0,
            'basis_std_pct': 0.0
        }

    # ── 0. Compute Fibonacci zone inline if not present ──
    fib_zone = 0
    if basis_col in df.columns and 'upper_1' in df.columns:
        last = df.iloc[-1]
        price = float(last['close'])
        levels = {}
        for col in ['basis', 'upper_1', 'upper_2', 'upper_3', 'upper_4', 'upper_5', 'upper_6',
                     'lower_1', 'lower_2', 'lower_3', 'lower_4', 'lower_5', 'lower_6']:
            if col in df.columns and pd.notna(last.get(col)):
                levels[col] = float(last[col])

        if levels:
            from app.analysis.fibonacci_bb import get_fibonacci_zone
            try:
                fib_zone = get_fibonacci_zone(price, levels)
            except Exception:
                fib_zone = 0

    # ── 1. Calcular pendiente del BASIS (skip NaN values) ──
    # Use only rows where basis is not NaN
    if basis_col in df.columns:
        valid_basis = df[basis_col].dropna()
        if len(valid_basis) >= lookback + 1:
            recent_basis = valid_basis.tail(lookback + 1)
            basis_start = float(recent_basis.iloc[0])
            basis_end = float(recent_basis.iloc[-1])
            basis_slope = (basis_end - basis_start) / basis_start if basis_start > 0 else 0.0
        elif len(valid_basis) >= 2:
            # Use whatever valid data we have
            basis_start = float(valid_basis.iloc[0])
            basis_end = float(valid_basis.iloc[-1])
            basis_slope = (basis_end - basis_start) / basis_start if basis_start > 0 else 0.0
        else:
            basis_slope = 0.0
    else:
        basis_slope = 0.0

    # ── 2. Calcular pendiente del EMA200 (skip NaN values) ──
    if ema200_col in df.columns:
        valid_ema = df[ema200_col].dropna()
        if len(valid_ema) >= lookback + 1:
            recent_ema = valid_ema.tail(lookback + 1)
            ema_start = float(recent_ema.iloc[0])
            ema_end = float(recent_ema.iloc[-1])
            ema200_slope = (ema_end - ema_start) / ema_start if ema_start > 0 else 0.0
        elif len(valid_ema) >= 2:
            ema_start = float(valid_ema.iloc[0])
            ema_end = float(valid_ema.iloc[-1])
            ema200_slope = (ema_end - ema_start) / ema_start if ema_start > 0 else 0.0
        else:
            ema200_slope = 0.0
    else:
        # Fallback: use EMA50 slope or close price slope
        if 'ema_50' in df.columns:
            valid_ema = df['ema_50'].dropna()
            if len(valid_ema) >= lookback + 1:
                recent_ema = valid_ema.tail(lookback + 1)
                ema_start = float(recent_ema.iloc[0])
                ema_end = float(recent_ema.iloc[-1])
                ema200_slope = (ema_end - ema_start) / ema_start if ema_start > 0 else 0.0
            else:
                ema200_slope = 0.0
        else:
            ema200_slope = 0.0

    # ── 3. Volatilidad del BASIS ──────────────
    if basis_col in df.columns:
        valid_basis_all = df[basis_col].dropna().tail(lookback)
        basis_vals = valid_basis_all.values.astype(float)
        basis_std = float(np.std(basis_vals)) / float(np.mean(basis_vals)) \
                    if len(basis_vals) > 0 and np.mean(basis_vals) > 0 else 0
    else:
        basis_std = 0.0

    # ── 4. Also compute close-price slope as complementary signal ──
    close_vals = df['close'].dropna().tail(lookback + 1)
    if len(close_vals) >= 2:
        close_start = float(close_vals.iloc[0])
        close_end = float(close_vals.iloc[-1])
        close_slope = (close_end - close_start) / close_start if close_start > 0 else 0.0
    else:
        close_slope = 0.0

    # ── 5. Clasificar por reglas ──────────────
    # Use a combined slope that considers both basis and price action
    # If basis slope is 0 (due to NaN), fall back to close slope
    effective_slope = basis_slope if abs(basis_slope) > 0.0001 else close_slope
    abs_slope = abs(effective_slope)
    abs_ema = abs(ema200_slope)

    if (effective_slope > slope_strong
            and ema200_slope > -slope_weak
            and fib_zone >= 1):
        movement_type = 'ascending'
        signal_bias   = 'long_bias'
        confidence    = min(abs_slope / slope_strong, 1.0)
        description   = (
            f'Tendencia alcista fuerte. '
            f'Slope +{effective_slope*100:.2f}% '
            f'en {lookback} velas. Zona Fib {fib_zone}.'
        )

    elif (effective_slope > slope_strong
            and fib_zone <= 0):
        # Strong upward slope but in lower fib zone = recovering
        movement_type = 'ascending'
        signal_bias   = 'long_bias'
        confidence    = min(abs_slope / slope_strong, 1.0) * 0.8
        description   = (
            f'Recuperación alcista. '
            f'Slope +{effective_slope*100:.2f}%. '
            f'Zona Fib {fib_zone}.'
        )

    elif (slope_weak < effective_slope <= slope_strong
              and fib_zone >= -1):
        movement_type = 'lateral_ascending'
        signal_bias   = 'long_bias'
        confidence    = 0.70
        description   = (
            f'Movimiento lateral ascendente. '
            f'Slope +{effective_slope*100:.2f}%.'
        )

    elif (fib_zone >= 3
              and abs_slope < slope_weak):
        movement_type = 'lateral_at_top'
        signal_bias   = 'short_bias'
        confidence    = 0.75
        description   = (
            f'Lateral en máximo. '
            f'Zona Fib {fib_zone}. '
            f'Posible distribución.'
        )

    elif (fib_zone <= -2
              and effective_slope > slope_weak):
        movement_type = 'ascending_from_low'
        signal_bias   = 'long_bias'
        confidence    = 0.65
        description   = (
            f'Ascenso desde mínimos. '
            f'Slope +{effective_slope*100:.2f}%, '
            f'Zona Fib {fib_zone}.'
        )

    elif (fib_zone >= 2
              and effective_slope < -slope_weak
              and ema200_slope >= -slope_weak):
        movement_type = 'descending_from_top'
        signal_bias   = 'short_bias'
        confidence    = 0.65
        description   = (
            f'Corrección desde máximo. '
            f'Slope {effective_slope*100:.2f}%, '
            f'Zona Fib {fib_zone}.'
        )

    elif (-slope_strong <= effective_slope < -slope_weak):
        movement_type = 'lateral_descending'
        signal_bias   = 'short_bias'
        confidence    = 0.70
        description   = (
            f'Lateral descendente. '
            f'Slope {effective_slope*100:.2f}%.'
        )

    elif (effective_slope < -slope_strong):
        movement_type = 'descending'
        signal_bias   = 'short_bias'
        confidence    = min(abs_slope / slope_strong, 1.0)
        description   = (
            f'Tendencia bajista. '
            f'Slope {effective_slope*100:.2f}%.'
        )

    else:
        movement_type = 'lateral'
        signal_bias   = 'neutral'
        confidence    = 0.60
        description   = (
            f'Movimiento lateral. '
            f'Slope {effective_slope*100:.2f}%, '
            f'zona Fib {fib_zone}.'
        )

    return {
        'movement_type':    movement_type,
        'basis_slope_pct':  round(effective_slope * 100, 4),
        'ema200_slope_pct': round(ema200_slope * 100, 4),
        'fib_zone_current': fib_zone,
        'basis_std_pct':    round(basis_std * 100, 4),
        'confidence':       round(confidence, 3),
        'signal_bias':      signal_bias,
        'description':      description,
    }

