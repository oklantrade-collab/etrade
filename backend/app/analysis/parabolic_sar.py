import pandas as pd
import numpy as np

def calculate_parabolic_sar(
    df:        pd.DataFrame,
    start:     float = 0.02,
    increment: float = 0.02,
    maximum:   float = 0.20
) -> pd.DataFrame:
    """
    Implementación exacta del SAR Parabólico
    de PineScript para replicar el indicador
    de TradingView.

    Parámetros por defecto estándar:
      start     = 0.02 (AF inicial)
      increment = 0.02 (incremento AF)
      maximum   = 0.20 (AF máximo)

    Agrega columnas al DataFrame:
      sar:             valor del SAR
      sar_trend:       1=alcista, -1=bajista
      sar_ini_high:    True cuando SAR cambia
                       de bajista a alcista
                       (b_sars_ini_high en Pine)
      sar_ini_low:     True cuando SAR cambia
                       de alcista a bajista
                       (b_sars_ini_low en Pine)
    """
    n = len(df)
    sar    = np.zeros(n)
    trend  = np.zeros(n, dtype=int)
    ep     = np.zeros(n)
    af_arr = np.zeros(n)

    # Inicializar primera vela
    sar[0]    = df['close'].iloc[0]
    trend[0]  = 0
    ep[0]     = df['close'].iloc[0]
    af_arr[0] = start

    for i in range(1, n):
        prev_trend = trend[i-1]
        prev_sar   = sar[i-1]
        prev_ep    = ep[i-1]
        prev_af    = af_arr[i-1]

        high_i  = df['high'].iloc[i]
        low_i   = df['low'].iloc[i]
        high_p1 = df['high'].iloc[i-1]
        low_p1  = df['low'].iloc[i-1]
        high_p2 = df['high'].iloc[i-2] \
                  if i >= 2 else high_p1
        low_p2  = df['low'].iloc[i-2] \
                  if i >= 2 else low_p1

        # Inicialización (trend == 0)
        if prev_trend == 0:
            if high_i >= high_p1 or low_i >= low_p1:
                trend[i] = 1
                sar[i]   = low_p1
                ep[i]    = high_p1
            else:
                trend[i] = -1
                sar[i]   = high_p1
                ep[i]    = low_p1
            af_arr[i] = start
            continue

        next_sar = prev_sar
        curr_af  = prev_af
        curr_ep  = prev_ep

        if prev_trend > 0:
            # Tendencia alcista
            if high_p1 > curr_ep:
                curr_ep = high_p1
                curr_af = min(maximum,
                              curr_af + increment)

            next_sar = prev_sar + \
                       curr_af * (curr_ep - prev_sar)
            next_sar = min(min(low_p1, low_p2),
                           next_sar)

            # Reversión a bajista
            if next_sar > low_i:
                trend[i]  = -1
                sar[i]    = curr_ep
                ep[i]     = low_i
                af_arr[i] = start
            else:
                trend[i]  = 1
                sar[i]    = next_sar
                ep[i]     = curr_ep
                af_arr[i] = curr_af

        else:
            # Tendencia bajista
            if low_p1 < curr_ep:
                curr_ep = low_p1
                curr_af = min(maximum,
                              curr_af + increment)

            next_sar = prev_sar + \
                       curr_af * (curr_ep - prev_sar)
            next_sar = max(max(high_p1, high_p2),
                           next_sar)

            # Reversión a alcista
            if next_sar < high_i:
                trend[i]  = 1
                sar[i]    = curr_ep
                ep[i]     = high_i
                af_arr[i] = start
            else:
                trend[i]  = -1
                sar[i]    = next_sar
                ep[i]     = curr_ep
                af_arr[i] = curr_af

    df['sar']       = sar
    df['sar_trend'] = trend

    # b_sars_ini_high: cambio de -1 a +1
    df['sar_ini_high'] = (
        (df['sar_trend'] == 1) &
        (df['sar_trend'].shift(1) == -1)
    )

    # b_sars_ini_low: cambio de +1 a -1
    df['sar_ini_low'] = (
        (df['sar_trend'] == -1) &
        (df['sar_trend'].shift(1) == 1)
    )

    return df


def analyze_structure(
    df:            pd.DataFrame,
    sar_col:       str   = 'sar_trend',
    n_confirm:     int   = 2,
    umbral_low:    float = 0.003,
    umbral_high:   float = 0.003
) -> dict:
    """
    Analiza la estructura de mercado comparando
    N velas consecutivas de High y Low.

    Para N=2 necesitamos al menos 3 velas:
      vela[-3], vela[-2], vela[-1]

    CONFIRMACIÓN DE 2 VELAS CONSECUTIVAS:

      LONG confirmado (Higher Lows × 2):
        low[-1] > low[-2] × (1 + umbral) Y
        low[-2] > low[-3] × (1 + umbral)

      Estructura LONG debilitada (Lower Lows × 2):
        low[-1] < low[-2] × (1 - umbral) Y
        low[-2] < low[-3] × (1 - umbral)

      SHORT confirmado (Lower Highs × 2):
        high[-1] < high[-2] × (1 - umbral) Y
        high[-2] < high[-3] × (1 - umbral)

      Estructura SHORT debilitada (Higher Highs × 2):
        high[-1] > high[-2] × (1 + umbral) Y
        high[-2] > high[-3] × (1 + umbral)
    """
    min_velas = n_confirm + 1
    if df is None or len(df) < min_velas:
        return {
            'structure':      'unknown',
            'allow_long':     True,
            'allow_short':    True,
            'reverse_signal': False,
            'reason':         f'Insuficientes velas ({len(df) if df is not None else 0})'
        }

    # Obtener las últimas n+1 velas
    recent   = df.tail(n_confirm + 1)
    sar_now  = int(recent[sar_col].iloc[-1])

    # Extraer highs y lows
    highs = [float(recent['high'].iloc[i])
             for i in range(n_confirm + 1)]
    lows  = [float(recent['low'].iloc[i])
             for i in range(n_confirm + 1)]

    # Verificar N consecutivos con umbral
    def all_higher_lows(lows_list, umbral):
        """Todos los lows suben >= umbral"""
        for i in range(1, len(lows_list)):
            if lows_list[i] < lows_list[i-1] * (1 + umbral):
                return False
        return True

    def all_lower_lows(lows_list, umbral):
        """Todos los lows bajan >= umbral"""
        for i in range(1, len(lows_list)):
            if lows_list[i] > lows_list[i-1] * (1 - umbral):
                return False
        return True

    def all_lower_highs(highs_list, umbral):
        """Todos los highs bajan >= umbral"""
        for i in range(1, len(highs_list)):
            if highs_list[i] > highs_list[i-1] * (1 - umbral):
                return False
        return True

    def all_higher_highs(highs_list, umbral):
        """Todos los highs suben >= umbral"""
        for i in range(1, len(highs_list)):
            if highs_list[i] < highs_list[i-1] * (1 + umbral):
                return False
        return True

    higher_lows  = all_higher_lows(lows, umbral_low)
    lower_lows   = all_lower_lows(lows, umbral_low)
    lower_highs  = all_lower_highs(highs, umbral_high)
    higher_highs = all_higher_highs(highs, umbral_high)

    curr_high = highs[-1]
    curr_low  = lows[-1]
    prev_high = highs[-2]
    prev_low  = lows[-2]

    # ── SAR POSITIVO ──────────────────────────────
    if sar_now > 0:
        if higher_lows:
            return {
                'sar_trend':      sar_now,
                'structure':      'confirmed',
                'allow_long':     True,
                'allow_short':    False,
                'reverse_signal': False,
                'curr_high':      curr_high,
                'curr_low':       curr_low,
                'prev_high':      prev_high,
                'prev_low':       prev_low,
                'reason': (
                    f'SAR+ | {n_confirm} Higher Lows '
                    f'confirmados → LONG válido'
                )
            }
        elif lower_lows:
            return {
                'sar_trend':      sar_now,
                'structure':      'weakened',
                'allow_long':     False,
                'allow_short':    True,
                'reverse_signal': True,
                'curr_high':      curr_high,
                'curr_low':       curr_low,
                'prev_high':      prev_high,
                'prev_low':       prev_low,
                'reason': (
                    f'SAR+ | {n_confirm} Lower Lows '
                    f'consecutivos (>{umbral_low*100:.1f}%) '
                    f'→ Estructura débil → SHORT autorizado'
                )
            }
        else:
            return {
                'sar_trend':      sar_now,
                'structure':      'neutral',
                'allow_long':     True,
                'allow_short':    False,
                'reverse_signal': False,
                'reason': (
                    f'SAR+ | Sin confirmación clara '
                    f'→ Mantener LONG por defecto'
                )
            }

    # ── SAR NEGATIVO ──────────────────────────────
    elif sar_now < 0:
        if lower_highs:
            return {
                'sar_trend':      sar_now,
                'structure':      'confirmed',
                'allow_long':     False,
                'allow_short':    True,
                'reverse_signal': False,
                'curr_high':      curr_high,
                'curr_low':       curr_low,
                'prev_high':      prev_high,
                'prev_low':       prev_low,
                'reason': (
                    f'SAR- | {n_confirm} Lower Highs '
                    f'confirmados → SHORT válido'
                )
            }
        elif higher_highs:
            return {
                'sar_trend':      sar_now,
                'structure':      'weakened',
                'allow_long':     True,
                'allow_short':    False,
                'reverse_signal': True,
                'curr_high':      curr_high,
                'curr_low':       curr_low,
                'prev_high':      prev_high,
                'prev_low':       prev_low,
                'reason': (
                    f'SAR- | {n_confirm} Higher Highs '
                    f'consecutivos (>{umbral_high*100:.1f}%) '
                    f'→ Estructura débil → LONG autorizado'
                )
            }
        else:
            return {
                'sar_trend':      sar_now,
                'structure':      'neutral',
                'allow_long':     False,
                'allow_short':    True,
                'reverse_signal': False,
                'reason': (
                    f'SAR- | Sin confirmación clara '
                    f'→ Mantener SHORT por defecto'
                )
            }

    # ── SAR NEUTRAL ───────────────────────────────
    return {
        'sar_trend':      0,
        'structure':      'neutral',
        'allow_long':     True,
        'allow_short':    True,
        'reverse_signal': False,
        'reason':         'SAR neutral → sin restricción'
    }

