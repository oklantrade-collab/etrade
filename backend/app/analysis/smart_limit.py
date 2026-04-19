import pandas as pd
import numpy as np

# Tabla de referencia de la imagen adjunta
ZONE_REFERENCE = {
    # n_trade: (zona_min, zona_max, señal, sizing_pct)
    (-6, -4): ('lower_4', 'lower_6', 'long_agresivo', 0.875),
    (-3, -3): ('lower_3', 'lower_3', 'long_media_alta', 0.75),
    (-2, -2): ('lower_2', 'lower_2', 'long_media',     0.50),
    (-1, -1): ('lower_1', 'lower_1', 'long_conservadora', 0.25),
    (0,  0):  ('basis',   'basis',   'neutral',         0.0),
    (1,  1):  ('upper_1', 'upper_1', 'short_conservadora', 0.25),
    (2,  6):  ('upper_2', 'upper_6', 'short_escalonado', 0.75),
}

def find_untouched_band(
    df:           pd.DataFrame,
    direction:    str,  # 'long' o 'short'
    lookback:     int = 50,
) -> dict:
    """
    Identifica la banda Fibonacci más cercana que
    el precio NO ha tocado en las últimas N velas.

    Para LONG: banda inferior inmediata no tocada
    Para SHORT: banda superior inmediata no tocada

    Returns:
      band_name:   str  (ej: 'upper_1', 'lower_3')
      band_value:  float
      last_touch_candles: int  (velas desde el último toque)
      is_untouched: bool  (True si no tocó en lookback)
      distance_pct: float  (% distancia desde precio actual)
    """
    recent = df.tail(lookback)
    price  = float(recent['close'].iloc[-1])

    if direction == 'long':
        bands = [
            ('lower_1', float(recent['lower_1'].iloc[-1])),
            ('lower_2', float(recent['lower_2'].iloc[-1])),
            ('lower_3', float(recent['lower_3'].iloc[-1])),
            ('lower_4', float(recent['lower_4'].iloc[-1])),
            ('lower_5', float(recent['lower_5'].iloc[-1])),
            ('lower_6', float(recent['lower_6'].iloc[-1])),
        ]
        # Para LONG: buscar la banda INFERIOR más cercana
        # que no fue tocada (el precio está por encima)
        candidate_bands = [
            (name, val) for name, val in bands
            if val < price  # banda está debajo del precio
        ]

    else:  # short
        bands = [
            ('upper_1', float(recent['upper_1'].iloc[-1])),
            ('upper_2', float(recent['upper_2'].iloc[-1])),
            ('upper_3', float(recent['upper_3'].iloc[-1])),
            ('upper_4', float(recent['upper_4'].iloc[-1])),
            ('upper_5', float(recent['upper_5'].iloc[-1])),
            ('upper_6', float(recent['upper_6'].iloc[-1])),
        ]
        candidate_bands = [
            (name, val) for name, val in bands
            if val > price  # banda está encima del precio
        ]

    results = []

    for band_name, band_value in candidate_bands:
        if band_value <= 0:
            continue

        # Contar cuántas velas tocaron esta banda
        # "tocar" = low (para lower) o high (para upper)
        # llegó dentro del 0.1% de la banda
        touch_threshold = band_value * 0.001  # 0.1%

        if direction == 'long':
            touches = recent[
                abs(recent['low'] - band_value)
                <= touch_threshold
            ].shape[0]
        else:
            touches = recent[
                abs(recent['high'] - band_value)
                <= touch_threshold
            ].shape[0]

        last_touch = lookback  # default: no tocó nunca
        if touches > 0:
            # Encontrar la vela más reciente que tocó
            if direction == 'long':
                mask = (
                    abs(recent['low'] - band_value)
                    <= touch_threshold
                )
            else:
                mask = (
                    abs(recent['high'] - band_value)
                    <= touch_threshold
                )
            touch_indices = recent[mask].index.tolist()
            if touch_indices:
                last_idx = recent.index.get_loc(
                    touch_indices[-1]
                )
                last_touch = lookback - last_idx

        distance_pct = abs(
            (band_value - price) / price * 100
        )

        results.append({
            'band_name':           band_name,
            'band_value':          band_value,
            'touches_in_lookback': touches,
            'last_touch_candles':  last_touch,
            'is_untouched':        touches == 0,
            'distance_pct':        round(distance_pct, 4),
        })

    if not results:
        return None

    # Ordenar: priorizar bandas NO tocadas
    # y más cercanas al precio actual
    untouched = [r for r in results if r['is_untouched']]
    touched   = sorted(
        [r for r in results if not r['is_untouched']],
        key=lambda x: x['last_touch_candles'],
        reverse=True  # más antigua primero
    )

    # Preferir la banda no tocada más cercana
    ranked = untouched + touched

    # Ordenar por distancia para tomar la más cercana
    ranked = sorted(
        ranked,
        key=lambda x: x['distance_pct']
    )

    return ranked[0] if ranked else None


def calculate_smart_limit_price(
    df:                pd.DataFrame,
    direction:         str,    # 'long' o 'short'
    movement_type:     str,    # del classify_movement()
    lookback:          int   = 50,
    margin_pct:        float = 0.0015,  # 0.15% margen
    min_margin_pct:    float = 0.0005,  # 0.05% mínimo
    max_margin_pct:    float = 0.0030,  # 0.30% máximo
) -> dict:
    """
    Calcula el precio LIMIT óptimo basado en:
      1. El tipo de movimiento actual
      2. La banda no tocada más cercana
      3. Un margen mínimo configurable

    El margen se ajusta según el tipo de movimiento:
      - Movimiento lateral:         margen mínimo (0.05%)
      - Lateral ascendente/desc:    margen medio  (0.15%)
      - Tendencia fuerte:           margen mayor  (0.30%)

    Returns:
      band_target:      str    (banda objetivo)
      band_value:       float  (valor de la banda)
      limit_price:      float  (precio de la orden LIMIT)
      margin_applied:   float  (% margen aplicado)
      movement_type:    str
      sizing_pct:       float  (sizing recomendado)
      signal_quality:   str    ('high' | 'medium' | 'low')
      rationale:        str    (explicación)
      fib_zone_entry:   int    (zona fib esperada al entrar)
    """

    # ── 1. Ajustar margen según movimiento ───────────
    MARGIN_BY_MOVEMENT = {
        'lateral':             min_margin_pct,
        'lateral_ascending':   margin_pct * 0.8,
        'ascending':           margin_pct,
        'lateral_at_top':      margin_pct * 1.2,
        'descending_from_top': margin_pct * 1.5,
        'lateral_descending':  margin_pct,
        'descending':          max_margin_pct,
    }
    margin = MARGIN_BY_MOVEMENT.get(
        movement_type, margin_pct
    )
    margin = max(min_margin_pct,
                 min(margin, max_margin_pct))

    # ── 2. Encontrar banda objetivo ──────────────────
    band_info = find_untouched_band(
        df, direction, lookback
    )

    if not band_info:
        return {
            'limit_price':    None,
            'rationale':      'No se encontró banda válida',
            'signal_quality': 'low',
            'band_target':    'none',
            'sizing_pct':     0.0,
            'distance_pct':   0.0,
            'is_untouched':   False,
            'last_touch_candles': 0
        }

    band_value = band_info['band_value']
    band_name  = band_info['band_name']
    price      = float(df['close'].iloc[-1])

    # ── 3. Calcular precio LIMIT con margen ──────────
    if direction == 'long':
        # LONG: colocar la orden LIGERAMENTE por encima
        # de la banda (para asegurar ejecución si precio
        # cae hasta la banda)
        limit_price = band_value * (1 + margin)
    else:
        # SHORT: colocar la orden LIGERAMENTE por debajo
        # de la banda superior
        limit_price = band_value * (1 - margin)

    # ── 4. Calcular sizing según la banda ────────────
    SIZING_BY_BAND = {
        'lower_1': 0.25,
        'lower_2': 0.50,
        'lower_3': 0.75,
        'lower_4': 0.875,
        'lower_5': 1.00,
        'lower_6': 1.00,
        'upper_1': 0.25,
        'upper_2': 0.50,
        'upper_3': 0.75,
        'upper_4': 0.875,
        'upper_5': 1.00,
        'upper_6': 1.00,
    }
    sizing = SIZING_BY_BAND.get(band_name, 0.50)

    # ── 5. Reducir sizing si movimiento adverso ──────
    ADVERSE_MOVEMENTS_LONG  = {
        'descending', 'lateral_descending',
        'descending_from_top'
    }
    ADVERSE_MOVEMENTS_SHORT = {
        'ascending', 'lateral_ascending'
    }

    if direction == 'long' and \
       movement_type in ADVERSE_MOVEMENTS_LONG:
        sizing = sizing * 0.50  # reducir a la mitad

    elif direction == 'short' and \
         movement_type in ADVERSE_MOVEMENTS_SHORT:
        sizing = sizing * 0.50

    # ── 6. Calidad de la señal ───────────────────────
    if band_info['is_untouched'] and \
       band_info['distance_pct'] < 3.0:
        quality = 'high'
    elif band_info['is_untouched']:
        quality = 'medium'
    else:
        quality = 'low'

    # Degradar calidad si movimiento adverso
    if direction == 'long' and \
       movement_type in ADVERSE_MOVEMENTS_LONG:
        quality = 'low'
    elif direction == 'short' and \
         movement_type in ADVERSE_MOVEMENTS_SHORT:
        quality = 'low'

    # ── 7. Calcular zona Fibonacci de entrada ────────
    # La zona en que estará el precio si llega al limit
    fib_zone_map = {
        'lower_1': -1, 'lower_2': -2, 'lower_3': -3,
        'lower_4': -4, 'lower_5': -5, 'lower_6': -6,
        'upper_1': 1,  'upper_2': 2,  'upper_3': 3,
        'upper_4': 4,  'upper_5': 5,  'upper_6': 6,
    }
    fib_zone_entry = fib_zone_map.get(band_name, 0)

    distance_pct = band_info['distance_pct']

    touch_desc = 'no tocada' if band_info['is_untouched'] else f"última vez hace {band_info['last_touch_candles']} velas"
    rationale = (
        f"Movimiento: {movement_type}. "
        f"Banda objetivo: {band_name} ({touch_desc}). "
        f"Distancia actual: {distance_pct:.2f}%. "
        f"Margen aplicado: {margin*100:.2f}%. "
        f"Sizing: {sizing*100:.0f}%."
    )

    return {
        'band_target':      band_name,
        'band_value':       round(band_value, 8),
        'limit_price':      round(limit_price, 8),
        'margin_applied':   round(margin * 100, 4),
        'movement_type':    movement_type,
        'sizing_pct':       round(sizing, 4),
        'signal_quality':   quality,
        'rationale':        rationale,
        'fib_zone_entry':   fib_zone_entry,
        'distance_pct':     distance_pct,
        'is_untouched':     band_info['is_untouched'],
        'last_touch_candles': band_info['last_touch_candles'],
    }
