"""
MÓDULO B — Profit Ladder (Escalera de Ganancias)

Monitorea el avance del precio a través de
las bandas Fibonacci y gestiona el momentum
con EMA3/EMA9.

Una vez que el precio cruza el BASIS (EMA20):
  → Activar monitoreo de EMA3 vs EMA9
  → Si EMA3 > EMA9: mantener (momentum alcista)
  → Si EMA3 < EMA9 por 2 velas: cerrar

Profit Floor (piso de ganancia por bandas):
  El piso sube cada vez que el precio alcanza
  una nueva banda Fibonacci.

Bollinger como contexto:
  Si Bollinger es inválido (muy estrecho):
  → Modo defensivo: cerrar al primer EMA3 < EMA9
"""

import pandas as pd
from app.core.logger import log_info


# Mapa de bandas Fibonacci (orden ascendente)
FIBONACCI_BANDS_LONG = [
    'lower_6', 'lower_5', 'lower_4', 'lower_3',
    'lower_2', 'lower_1', 'basis',
    'upper_1', 'upper_2', 'upper_3',
    'upper_4', 'upper_5', 'upper_6',
]
FIBONACCI_BANDS_SHORT = list(
    reversed(FIBONACCI_BANDS_LONG)
)

# Profit Floor: cuando alcanzas X → el piso es Y
PROFIT_FLOOR_MAP_LONG = {
    # banda_alcanzada: banda_piso_minima
    'upper_1': 'basis',
    'upper_2': 'lower_1',
    'upper_3': 'basis',
    'upper_4': 'upper_1',
    'upper_5': 'upper_2',
    'upper_6': 'upper_3',
}
PROFIT_FLOOR_MAP_SHORT = {
    'lower_1': 'basis',
    'lower_2': 'upper_1',
    'lower_3': 'basis',
    'lower_4': 'lower_1',
    'lower_5': 'lower_2',
    'lower_6': 'lower_3',
}


def get_current_band(
    price: float,
    snap:  dict,
    side:  str,
) -> dict:
    """
    Determina en qué banda Fibonacci está
    el precio actualmente.
    """
    basis = float(snap.get('basis', 0))
    is_long = side in ('long', 'buy')

    # Construir mapa de bandas
    bands = {'basis': basis}
    for n in range(1, 7):
        bands[f'upper_{n}'] = float(
            snap.get(f'upper_{n}', 0)
        )
        bands[f'lower_{n}'] = float(
            snap.get(f'lower_{n}', 0)
        )

    # Determinar banda actual
    current_band = 'basis'
    current_price_band = basis

    if is_long:
        # Buscar la banda más alta que el precio
        # ha superado
        for band in FIBONACCI_BANDS_LONG:
            val = bands.get(band, 0)
            if val > 0 and price >= val:
                current_band       = band
                current_price_band = val
    else:
        for band in FIBONACCI_BANDS_SHORT:
            val = bands.get(band, 0)
            if val > 0 and price <= val:
                current_band       = band
                current_price_band = val

    return {
        'current_band':  current_band,
        'band_price':    current_price_band,
        'basis':         basis,
        'above_basis':   price > basis if basis > 0 else False,
        'bands':         bands,
    }


def update_profit_floor(
    current_band: str,
    snap:         dict,
    side:         str,
    existing_floor: str = None,
) -> dict:
    """
    Actualiza el Profit Floor basado en
    la banda actual alcanzada.

    El piso NUNCA baja (solo sube para LONG,
    solo baja para SHORT).
    """
    is_long    = side in ('long', 'buy')
    floor_map  = (
        PROFIT_FLOOR_MAP_LONG
        if is_long else
        PROFIT_FLOOR_MAP_SHORT
    )

    new_floor_band  = floor_map.get(
        current_band, existing_floor
    )

    if not new_floor_band:
        return {
            'floor_band':  existing_floor,
            'floor_price': 0,
            'updated':     False,
        }

    floor_price = float(
        snap.get(new_floor_band, 0)
    )

    return {
        'floor_band':  new_floor_band,
        'floor_price': floor_price,
        'updated':     new_floor_band != existing_floor,
        'reason': (
            f'Banda {current_band} alcanzada → '
            f'piso sube a {new_floor_band} '
            f'(${floor_price:.5f})'
        ),
    }


def check_basis_crossed(
    position:      dict,
    current_price: float,
    snap:          dict,
    df_15m:        pd.DataFrame,
) -> dict:
    """
    Verifica si el precio cruzó el BASIS
    (EMA20) de forma confirmada.

    Confirmación: precio > BASIS por 2 velas
    consecutivas (evitar falsas señales).
    """
    already_crossed = bool(
        position.get('basis_crossed', False)
    )
    if already_crossed:
        return {
            'crossed':   True,
            'confirmed': True,
            'reason':    'BASIS ya cruzado anteriormente',
        }

    basis = float(snap.get('basis', 0))
    if basis <= 0:
        return {'crossed': False, 'confirmed': False, 'reason': 'BASIS <= 0 (no disponible)'}

    side    = str(position.get('side', 'long'))
    is_long = side in ('long', 'buy')

    # Verificar 2 velas consecutivas sobre BASIS
    if df_15m is not None and len(df_15m) >= 3:
        closes = [
            float(df_15m.iloc[-2].get('close', 0)),
            float(df_15m.iloc[-3].get('close', 0)),
        ]
        if is_long:
            confirmed = all(c > basis for c in closes)
        else:
            confirmed = all(c < basis for c in closes)
    else:
        confirmed = (
            current_price > basis if is_long
            else current_price < basis
        )

    return {
        'crossed':   confirmed,
        'confirmed': confirmed,
        'basis':     basis,
        'price':     current_price,
        'reason': (
            f'BASIS={basis:.5f}: '
            f'{"cruzado ✅" if confirmed else "no cruzado"} '
            f'({current_price:.5f})'
        ),
    }


def check_ema_momentum(
    df_15m:       pd.DataFrame,
    fast_period:  int = 3,
    slow_period:  int = 9,
    consec_needed: int = 2,
) -> dict:
    """
    Verifica el estado de EMA3 vs EMA9.

    Para confirmar pérdida de momentum:
      EMA3 < EMA9 por N velas consecutivas
      (default: 2 velas para evitar falsas señales)

    Retorna:
      is_fast_above:   bool (EMA3 > EMA9)
      consec_below:    int (velas consecutivas
                       con EMA3 < EMA9)
      momentum_lost:   bool (momentum perdido)
    """
    if df_15m is None or len(df_15m) < slow_period + 2:
        return {
            'is_fast_above': True,
            'consec_below':  0,
            'momentum_lost': False,
            'ema_fast':      0,
            'ema_slow':      0,
            'valid':         False,
        }

    closes = pd.to_numeric(
        df_15m['close'], errors='coerce'
    ).dropna()

    ema_fast = closes.ewm(
        span=fast_period, adjust=False
    ).mean()
    ema_slow = closes.ewm(
        span=slow_period, adjust=False
    ).mean()

    # Contar velas consecutivas con EMA3 < EMA9
    consec_below = 0
    for i in range(1, min(consec_needed + 2, len(closes))):
        if ema_fast.iloc[-i] < ema_slow.iloc[-i]:
            consec_below += 1
        else:
            break

    is_fast_above = float(ema_fast.iloc[-1]) > \
                    float(ema_slow.iloc[-1])
    momentum_lost = consec_below >= consec_needed

    return {
        'is_fast_above': is_fast_above,
        'consec_below':  consec_below,
        'momentum_lost': momentum_lost,
        'ema_fast':      round(float(ema_fast.iloc[-1]), 6),
        'ema_slow':      round(float(ema_slow.iloc[-1]), 6),
        'valid':         True,
        'reason': (
            f'EMA3={ema_fast.iloc[-1]:.4f} '
            f'{">" if is_fast_above else "<"} '
            f'EMA9={ema_slow.iloc[-1]:.4f}. '
            f'EMA3<EMA9 por {consec_below} velas '
            f'{"→ MOMENTUM PERDIDO ⚠️" if momentum_lost else ""}'
        ),
    }


def check_bollinger_validity(
    snap:        dict,
    market_type: str = 'crypto_futures',
) -> dict:
    """
    Verifica si el Bollinger Band es válido
    como referencia.

    Bollinger INVÁLIDO (muy estrecho):
      bb_width < bb_invalid_width_pct del precio
      → Mercado en consolidación
      → Modo defensivo: cerrar al primer EMA cross

    Bollinger VÁLIDO:
      Hay espacio para moverse
      → Modo normal: esperar EMA confirmado
    """
    from app.strategy.profit_capture import (
        CAPTURE_CONFIG
    )
    cfg      = CAPTURE_CONFIG.get(market_type, {})
    min_w    = float(
        cfg.get('bb_invalid_width_pct', 0.005)
    ) * 100

    bb_upper = float(snap.get(
        'bb_upper',
        snap.get('upper_bollinger', 0)
    ))
    bb_lower = float(snap.get(
        'bb_lower',
        snap.get('lower_bollinger', 0)
    ))
    price    = float(snap.get('price', 0))

    if bb_upper <= 0 or bb_lower <= 0 or price <= 0:
        return {
            'valid':     False,
            'width_pct': 0,
            'reason':    'Bollinger no disponible',
        }

    width_pct = (bb_upper - bb_lower) / price * 100
    valid     = width_pct >= min_w

    return {
        'valid':       valid,
        'bb_upper':    bb_upper,
        'bb_lower':    bb_lower,
        'width_pct':   round(width_pct, 4),
        'min_width':   min_w,
        'reason': (
            f'BB width={width_pct:.3f}% '
            f'{"≥" if valid else "<"} '
            f'{min_w:.3f}% → '
            f'{"VÁLIDO ✅" if valid else "INVÁLIDO ⚠️ (modo defensivo)"}'
        ),
    }


def evaluate_profit_ladder(
    symbol:        str,
    side:          str,
    position:      dict,
    current_price: float,
    snap:          dict,
    df_15m:        pd.DataFrame,
    market_type:   str = 'crypto_futures',
) -> dict:
    """
    Función principal del MÓDULO B.

    Evalúa el avance del precio en las bandas
    Fibonacci y gestiona el momentum con EMA3/EMA9.

    Solo actúa DESPUÉS de que el precio cruzó
    el BASIS (EMA20) desde la banda de entrada.

    Retorna:
      action: 'hold' | 'close' | 'update_floor'
      reason: str
    """
    side    = str(position.get('side', 'long'))
    is_long = side in ('long', 'buy')

    # ── 1. Verificar cruce del BASIS ───────────
    basis_check = check_basis_crossed(
        position, current_price, snap, df_15m
    )

    if not basis_check['crossed']:
        return {
            'action': 'hold',
            'reason': (
                f'Precio aún no cruzó el BASIS — '
                f'módulo B inactivo. '
                f'{basis_check["reason"]}'
            ),
        }

    # ── 2. Banda actual ────────────────────────
    band_data = get_current_band(
        current_price, snap, side
    )
    current_band  = band_data['current_band']

    # ── 3. Actualizar Profit Floor ─────────────
    existing_floor = position.get(
        'profit_floor_band'
    )
    floor_data = update_profit_floor(
        current_band, snap, side, existing_floor
    )

    # ── 4. Verificar Bollinger ─────────────────
    bb_check = check_bollinger_validity(
        snap, market_type
    )

    # ── 5. EMA3 vs EMA9 momentum ──────────────
    consec_needed = 1 if not bb_check['valid'] \
                    else 2
    # En modo defensivo (BB inválido) → 1 vela
    # En modo normal → 2 velas confirmadas

    ema_check = check_ema_momentum(
        df_15m,
        consec_needed=consec_needed,
    )

    # ── 6. Verificar Profit Floor breach ──────
    floor_price  = float(
        position.get('profit_floor_price') or 0
    )
    floor_breached = False
    if floor_price > 0:
        if is_long:
            floor_breached = current_price < floor_price
        else:
            floor_breached = current_price > floor_price

    # ── 7. Tomar decisión ─────────────────────

    # ── 7b. Filtro de Acción del Precio (Low/High de la Vela) ──
    price_action_exit = True
    if df_15m is not None and len(df_15m) >= 2:
        try:
            if is_long:
                low_active = float(df_15m['low'].iloc[-1])
                low_prev   = float(df_15m['low'].iloc[-2])
                price_action_exit = low_active < low_prev
            else:
                high_active = float(df_15m['high'].iloc[-1])
                high_prev   = float(df_15m['high'].iloc[-2])
                price_action_exit = high_active > high_prev
        except Exception:
            pass

    # ── 7c. Calcular PNL Actual ─────────────────
    entry = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
    pnl_pct = 0.0
    if entry > 0:
        if is_long:
            pnl_pct = (current_price - entry) / entry * 100
        else:
            pnl_pct = (entry - current_price) / entry * 100

    # CIERRE por pérdida de momentum (EMA)
    if ema_check['momentum_lost']:
        # Solo permitimos el cierre defensivo de la escalera si estamos en ganancia.
        # Si el trade está en pérdida, dejamos que el SL o Smart Exit actúe, no el Profit Ladder.
        if pnl_pct > 0:
            if price_action_exit:
                mode = 'defensivo' if not bb_check['valid'] \
                       else 'normal'
                return {
                    'action':       'close',
                    'reason': (
                        f'MOMENTUM PERDIDO [modo {mode}]: '
                        f'EMA3{"<" if is_long else ">"}EMA9 por '
                        f'{ema_check["consec_below"]} velas Y rotura de precio '
                        f'({"Low" if is_long else "High"} actual {"<" if is_long else ">"} anterior)'
                    ),
                    'triggered_by':  'ema_cross_confirmed',
                    'current_band':  current_band,
                    'bb_valid':      bb_check['valid'],
                    'consec_below':  ema_check['consec_below'],
                    'floor_data':    floor_data,
                }
            else:
                log_info('PROFIT', f'📊 EXIT FILTRADO [{symbol}]: EMA {"<" if is_long else ">"} EMA9 pero Accion de Precio sostiene ({"Low" if is_long else "High"} actual >= anterior). Esperando...')
        else:
            log_info('PROFIT', f'📊 EXIT FILTRADO [{symbol}]: EMA {"<" if is_long else ">"} EMA9 pero PNL ({pnl_pct:.2f}%) <= 0. Profit Ladder exige ganancia.')

    # CIERRE por violación del Profit Floor
    if floor_breached:
        if pnl_pct > 0:
            return {
                'action':      'close',
                'reason': (
                    f'PROFIT FLOOR VIOLADO: '
                    f'precio {current_price:.5f} '
                    f'cruzó el piso '
                    f'{floor_price:.5f} '
                    f'({position.get("profit_floor_band")}). '
                    f'Cerrar para proteger ganancia.'
                ),
                'triggered_by': 'profit_floor_breach',
                'current_band': current_band,
                'floor_band':   position.get('profit_floor_band'),
                'floor_price':  floor_price,
            }
        else:
            log_info('PROFIT', f'📊 EXIT FILTRADO [{symbol}]: Floor Breached pero PNL ({pnl_pct:.2f}%) <= 0. Profit Ladder exige ganancia.')

    # Actualizar el Profit Floor si mejoró
    if floor_data.get('updated'):
        return {
            'action':       'update_floor',
            'new_floor_band': floor_data['floor_band'],
            'new_floor_price': floor_data['floor_price'],
            'current_band': current_band,
            'ema_ok':       ema_check['is_fast_above'],
            'bb_valid':     bb_check['valid'],
            'reason': (
                f'Profit Floor actualizado: '
                f'{floor_data["reason"]}. '
                f'EMA OK={ema_check["is_fast_above"]}. '
                f'Banda={current_band}'
            ),
        }

    # HOLD: momentum activo, sin señal de cierre
    return {
        'action':      'hold',
        'current_band': current_band,
        'ema_ok':      ema_check['is_fast_above'],
        'bb_valid':    bb_check['valid'],
        'floor_band':  existing_floor,
        'reason': (
            f'Mantener: EMA3>EMA9, '
            f'banda={current_band}, '
            f'piso={existing_floor}, '
            f'BB={"OK" if bb_check["valid"] else "ESTRECHO"}'
        ),
    }
