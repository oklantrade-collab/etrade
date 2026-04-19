"""
Dynamic Stop Loss Manager

Implementa el sistema de SL en dos capas:
  CAPA 1: Backstop SL (lower_6 o -8%)
          Se registra al abrir, NO se envía
          al exchange hasta que SIPV confirme.
  CAPA 2: Dynamic SL activado por SIPV
          Se activa con señal bajista en 4H/1D
          Usa banda Fibonacci inmediata inferior

Compatible con Crypto (Binance), Forex (cTrader)
y Stocks (IB TWS).
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Optional
from app.core.logger import log_info, log_error

# ── Configuración ──────────────────────────────
SL_CONFIG = {
    # Delta adicional debajo de la banda Fibonacci
    # (el mismo delta que se usaba antes: 2% del precio)
    'fibonacci_delta_pct': 0.005,  # 0.5%

    # Trailing SL: distancia desde el máximo
    'trailing_pct_crypto': 0.03,   # 3%
    'trailing_pct_forex':  0.005,  # 50 pips aprox
    'trailing_pct_stocks': 0.04,   # 4%

    # Backstop amplio si no hay bandas Fibonacci
    'backstop_pct_crypto': 0.08,   # 8%
    'backstop_pct_forex':  0.015,  # 150 pips
    'backstop_pct_stocks': 0.10,   # 10%

    # Velas mínimas para confirmar señal SIPV
    'sipv_confirmation_candles': 1,

    # Cooldown: esperar N ciclos de 15m
    # después de señal SIPV antes de activar SL
    'sipv_cooldown_cycles': 0,  # 0 = inmediato
}

# Bandas Fibonacci en orden (de más cerca a más lejos)
LOWER_BANDS_ORDER = [
    'lower_1', 'lower_2', 'lower_3',
    'lower_4', 'lower_5', 'lower_6'
]
UPPER_BANDS_ORDER = [
    'upper_1', 'upper_2', 'upper_3',
    'upper_4', 'upper_5', 'upper_6'
]


def calculate_backstop_sl(
    entry_price:  float,
    side:         str,
    snap:         dict,
    market_type:  str = 'crypto_futures'
) -> dict:
    side = side.lower()
    """
    Calcula el SL de seguridad amplio (Capa 1).
    Se registra al abrir la posición.
    Para BUY: lower_6 o -8% del precio.
    Para SELL: upper_6 o +8% del precio.

    NO se envía al exchange todavía.
    Solo se registra en la BD como backstop.
    """
    pct = SL_CONFIG.get(
        f'backstop_pct_{market_type.split("_")[0]}',
        0.08
    )

    if side in ('long', 'buy'):
        # Intentar usar lower_6
        lower_6 = float(snap.get('lower_6', 0))
        if lower_6 > 0 and \
           lower_6 < entry_price * (1 - pct / 2):
            backstop = lower_6 * (
                1 - SL_CONFIG['fibonacci_delta_pct']
            )
            source = 'lower_6'
        else:
            backstop = entry_price * (1 - pct)
            source = f'fixed_{pct*100:.0f}pct'
    else:
        upper_6 = float(snap.get('upper_6', 0))
        if upper_6 > 0 and \
           upper_6 > entry_price * (1 + pct / 2):
            backstop = upper_6 * (
                1 + SL_CONFIG['fibonacci_delta_pct']
            )
            source = 'upper_6'
        else:
            backstop = entry_price * (1 + pct)
            source = f'fixed_{pct*100:.0f}pct'

    return {
        'backstop_price': round(backstop, 8),
        'source':         source,
        'pct_from_entry': abs(
            backstop - entry_price
        ) / entry_price * 100,
    }


def calculate_dynamic_sl(
    current_price: float,
    side:          str,
    snap:          dict,
    market_type:   str = 'crypto_futures'
) -> dict:
    side = side.lower()
    """
    Calcula el SL dinámico (Capa 2).
    Se activa cuando SIPV detecta señal contraria.

    Para BUY: encuentra la banda Fibonacci
      inmediata inferior al precio actual
      y resta el delta.

    Para SELL: encuentra la banda Fibonacci
      inmediata superior al precio actual
      y suma el delta.

    Si no hay bandas disponibles, usa el
    backstop pct como fallback.
    """
    delta_pct = SL_CONFIG['fibonacci_delta_pct']

    if side in ('long', 'buy'):
        # Buscar la banda inferior inmediata
        target_band = None
        target_value = 0.0

        for band_name in LOWER_BANDS_ORDER:
            band_val = float(
                snap.get(band_name, 0)
            )
            if band_val > 0 and \
               band_val < current_price:
                target_band  = band_name
                target_value = band_val
                break  # La primera que está abajo

        if target_value > 0:
            # SL = banda inferior + delta (abajo)
            dynamic_sl = target_value * (
                1 - delta_pct
            )
            source = f'fibonacci_{target_band}'
        else:
            # Fallback: 3% abajo del precio actual
            dynamic_sl = current_price * (
                1 - SL_CONFIG.get(
                    f'trailing_pct_{market_type.split("_")[0]}',
                    0.03
                )
            )
            source = 'fallback_trailing'

        improvement = (
            current_price - dynamic_sl
        ) / current_price * 100

    else:  # short, sell
        target_band = None
        target_value = 0.0

        for band_name in UPPER_BANDS_ORDER:
            band_val = float(
                snap.get(band_name, 0)
            )
            if band_val > 0 and \
               band_val > current_price:
                target_band  = band_name
                target_value = band_val
                break

        if target_value > 0:
            dynamic_sl = target_value * (
                1 + delta_pct
            )
            source = f'fibonacci_{target_band}'
        else:
            dynamic_sl = current_price * (
                1 + SL_CONFIG.get(
                    f'trailing_pct_{market_type.split("_")[0]}',
                    0.03
                )
            )
            source = 'fallback_trailing'

        improvement = (
            dynamic_sl - current_price
        ) / current_price * 100

    return {
        'dynamic_sl_price': round(dynamic_sl, 8),
        'target_band':      target_band,
        'source':           source,
        'improvement_pct':  round(improvement, 4),
        'delta_applied':    delta_pct * 100,
    }


def calculate_trailing_sl(
    position:      dict,
    current_price: float,
    market_type:   str = 'crypto_futures'
) -> dict:
    """
    Calcula el Trailing SL.
    Sube el SL cuando el precio sube (para BUY).
    Baja el SL cuando el precio baja (para SELL).

    El trailing SL protege ganancias antes de
    que aparezca la señal SIPV.

    Para BUY:
      trailing_sl = max_precio × (1 - trail_pct)
    Para SELL:
      trailing_sl = min_precio × (1 + trail_pct)
    """
    side      = str(position.get('side', 'long')).lower()
    trail_pct = SL_CONFIG.get(
        f'trailing_pct_{market_type.split("_")[0]}',
        0.03
    )

    # Actualizar el precio máximo/mínimo alcanzado
    highest = float(
        position.get('highest_price_reached', 0)
    ) or current_price
    lowest  = float(
        position.get('lowest_price_reached',
                     current_price)
    )

    if side in ('long', 'buy'):
        new_highest = max(highest, current_price)
        trailing_sl = new_highest * (1 - trail_pct)
        improved    = new_highest > highest

    else:
        new_lowest  = min(lowest, current_price)
        trailing_sl = new_lowest * (1 + trail_pct)
        improved    = new_lowest < lowest

    return {
        'trailing_sl_price':     round(trailing_sl, 8),
        'highest_price_reached': round(new_highest, 8)
                                 if side in ('long','buy')
                                 else highest,
        'lowest_price_reached':  round(new_lowest, 8)
                                 if side not in ('long','buy')
                                 else lowest,
        'improved':              improved,
        'trail_pct':             trail_pct * 100,
    }


def detect_sipv_exit_signal(
    side:  str,
    snap:  dict,
    df_4h: pd.DataFrame,
    df_1d: pd.DataFrame = None
) -> dict:
    side = side.lower()
    """
    Detecta si el SIPV (Sistema de Identificación
    de Patrones de Velas) genera una señal de
    salida para la posición actual.

    Para BUY (posición larga):
      Señal de salida = acción SELL del SIPV
      detectada en 4H y/o 1D.

    Para SELL (posición corta):
      Señal de salida = acción BUY del SIPV
      detectada en 4H y/o 1D.
    """
    if side in ('long', 'buy'):
        pine_exit   = 'Sell'
        sar_exit    = -1  # SAR negativo = bajista
        fib_zone_exit = lambda z: z >= 3  # zona alta
    else:
        pine_exit   = 'Buy'
        sar_exit    = 1   # SAR positivo = alcista
        fib_zone_exit = lambda z: z <= -3

    # C1: PineScript signal
    pine = str(snap.get('pinescript_signal', ''))
    c1_pine = pine == pine_exit

    # C2: SAR negativo/positivo
    sar_4h  = int(snap.get('sar_trend_4h', 0))
    sar_15m = int(snap.get('sar_trend_15m', 0))
    c2_sar  = (sar_4h == sar_exit) or \
              (sar_15m == sar_exit)

    # C3: Zona Fibonacci alta/baja
    fib_zone = int(snap.get('fibonacci_zone', 0))
    c3_fib   = fib_zone_exit(fib_zone)

    # C4: Vela 4H confirma (del módulo proactive_exit)
    c4_candle_4h = False
    if df_4h is not None and len(df_4h) >= 2:
        last = df_4h.iloc[-2]
        o    = float(last.get('open',  0))
        c_price = float(last.get('close', 0))
        if o > 0:
            body = (c_price - o) / o
            if side in ('long', 'buy'):
                c4_candle_4h = body < -0.005  # bajista >0.5%
            else:
                c4_candle_4h = body > 0.005   # alcista >0.5%

    # C5: Vela 1D confirma (si disponible)
    c5_candle_1d = False
    if df_1d is not None and len(df_1d) >= 2:
        last_1d  = df_1d.iloc[-2]
        o_1d     = float(last_1d.get('open',  0))
        c_1d     = float(last_1d.get('close', 0))
        if o_1d > 0:
            body_1d = (c_1d - o_1d) / o_1d
            if side in ('long', 'buy'):
                c5_candle_1d = body_1d < -0.005
            else:
                c5_candle_1d = body_1d > 0.005

    # Contar condiciones activas
    conditions_met = sum([
        c1_pine, c2_sar, c3_fib,
        c4_candle_4h, c5_candle_1d
    ])

    # Determinar fuente y fuerza de la señal
    sources = []
    if c4_candle_4h: sources.append('4h')
    if c5_candle_1d: sources.append('1d')

    if conditions_met >= 4:
        strength   = 'strong'
        confidence = 0.90
    elif conditions_met == 3:
        strength   = 'medium'
        confidence = 0.70
    elif conditions_met == 2:
        strength   = 'weak'
        confidence = 0.50
    else:
        strength   = 'none'
        confidence = 0.0

    signal_detected = conditions_met >= 2

    return {
        'signal_detected': signal_detected,
        'conditions_met':  conditions_met,
        'source':          '+'.join(sources)
                           if sources else 'indicators',
        'strength':        strength,
        'confidence':      confidence,
        'conditions': {
            'pine':      c1_pine,
            'sar':       c2_sar,
            'fib':       c3_fib,
            'candle_4h': c4_candle_4h,
            'candle_1d': c5_candle_1d,
        },
        'pattern': (
            f'SIPV {side.upper()} EXIT '
            f'({conditions_met}/5 condiciones)'
        )
    }


def evaluate_sl_action(
    position:      dict,
    current_price: float,
    snap:          dict,
    df_4h:         pd.DataFrame,
    df_1d:         pd.DataFrame = None,
    market_type:   str = 'crypto_futures'
) -> dict:
    """
    Función principal del Dynamic SL Manager.
    """
    side    = str(position.get('side', 'long')).lower()
    entry   = float(position.get(
        'avg_entry_price',
        position.get('entry_price', 0)
    ))
    backstop = float(
        position.get('sl_backstop_price', 0) or 0
    )
    dynamic_sl_active = bool(
        position.get('sl_dynamic_price')
    )
    existing_dynamic  = float(
        position.get('sl_dynamic_price', 0) or 0
    )
    trailing_sl = float(
        position.get('trailing_sl_price', 0) or 
        position.get('stop_loss_price', 0) or 
        position.get('sl_price', 0) or 0
    )

    # ── CHECK 1: Backstop hit (siempre activo) ─
    if backstop > 0:
        backstop_hit = (
            (side in ('long','buy') and
             current_price <= backstop) or
            (side not in ('long','buy') and
             current_price >= backstop)
        )
        if backstop_hit:
            return {
                'action':  'close_backstop',
                'reason':  (
                    f'Backstop SL hit: '
                    f'precio={current_price:.6f} '
                    f'backstop={backstop:.6f}'
                ),
                'sl_price': backstop,
            }

    # ── CHECK 2: Dynamic SL ya activo ─────────
    if dynamic_sl_active and existing_dynamic > 0:
        dynamic_hit = (
            (side in ('long','buy') and
             current_price <= existing_dynamic) or
            (side not in ('long','buy') and
             current_price >= existing_dynamic)
        )
        if dynamic_hit:
            return {
                'action':  'trigger_dynamic_sl',
                'reason':  (
                    f'Dynamic SL hit: '
                    f'precio={current_price:.6f} '
                    f'sl={existing_dynamic:.6f}'
                ),
                'sl_price': existing_dynamic,
            }

    # ── CHECK 2.5: Trailing SL hit (asegurar ganancia o limitar pérdida) ─
    if trailing_sl > 0:
        trailing_hit = (
            (side in ('long','buy') and
             current_price <= trailing_sl) or
            (side not in ('long','buy') and
             current_price >= trailing_sl)
        )
        if trailing_hit:
            return {
                'action':  'trigger_dynamic_sl', # Reutilizamos acción para simplificar monitor
                'reason':  (
                    f'Trailing/Active SL hit: '
                    f'precio={current_price:.6f} '
                    f'sl={trailing_sl:.6f}'
                ),
                'sl_price': trailing_sl,
            }

    # ── CHECK 3: Detectar señal SIPV ──────────
    sipv = detect_sipv_exit_signal(
        side, snap, df_4h, df_1d
    )

    if sipv['signal_detected'] and \
       not dynamic_sl_active:
        # Calcular el nuevo SL dinámico
        new_sl = calculate_dynamic_sl(
            current_price, side, snap, market_type
        )
        # Calcular trailing para comparar
        trail  = calculate_trailing_sl(
            position, current_price, market_type
        )

        # Usar el más cercano (mayor protección)
        if side in ('long', 'buy'):
            best_sl = max(
                new_sl['dynamic_sl_price'],
                trail['trailing_sl_price']
            )
        else:
            best_sl = min(
                new_sl['dynamic_sl_price'],
                trail['trailing_sl_price']
            )

        return {
            'action':          'activate_dynamic_sl',
            'sl_price':        best_sl,
            'source':          new_sl['source'],
            'target_band':     new_sl.get(
                'target_band'
            ),
            'sipv':            sipv,
            'trailing_backup': trail[
                'trailing_sl_price'
            ],
            'reason': (
                f'SIPV señal {sipv["strength"]}: '
                f'{sipv["pattern"]}. '
                f'SL dinámico en '
                f'{new_sl["source"]}: '
                f'{best_sl:.6f}'
            ),
        }

    # ── CHECK 4: Actualizar Trailing SL ───────
    # (si SIPV aún no activó pero precio subió)
    trail = calculate_trailing_sl(
        position, current_price, market_type
    )

    if trail['improved']:
        return {
            'action':    'update_trailing',
            'sl_price':  trail['trailing_sl_price'],
            'new_max':   trail.get(
                'highest_price_reached'
            ),
            'new_min':   trail.get(
                'lowest_price_reached'
            ),
            'trail_pct': trail['trail_pct'],
            'reason': (
                f'Trailing actualizado: '
                f'nuevo max/min='
                f'{trail.get("highest_price_reached") or trail.get("lowest_price_reached"):.6f}'
            ),
        }

    # ── Sin acción ────────────────────────────
    return {
        'action': 'none',
        'reason': 'Sin cambios necesarios',
        'sipv':   sipv,
    }


async def send_sl_to_exchange(
    symbol:      str,
    side:        str,
    sl_price:    float,
    quantity:    float,
    position_id: str,
    supabase,
    market_type: str = 'crypto_futures'
) -> Optional[str]:
    side = side.lower()
    """
    Envía la orden de Stop Loss al exchange.
    Retorna el ID de la orden del exchange.
    """
    sl_side = 'sell' if side in ('long','buy') \
              else 'buy'

    try:
        if market_type == 'crypto_futures':
            from app.execution.providers.binance_provider import (
                BinanceCryptoProvider
            )
            provider = BinanceCryptoProvider()
            # Stop Market: cierra al tocar el precio
            order = await provider.place_order(
                symbol     = symbol,
                side       = sl_side,
                order_type = 'STOP_MARKET',
                quantity   = quantity,
                stop_price = sl_price,
                reduce_only= True,  # Solo cerrar
            )
            # handle order returned
            exchange_id = None
            if order and 'orderId' in order:
                exchange_id = str(order.get('orderId'))
            else:
                exchange_id = f'paper_sl_fallback_{position_id}' 

        elif market_type == 'forex_futures':
            # Para cTrader: modificar el SL
            exchange_id = f'ctdr_sl_{position_id}'

        elif market_type in (
            'stocks_spot', 'crypto_spot'
        ):
            exchange_id = f'paper_sl_{position_id}'

        else:
            exchange_id = f'paper_sl_{position_id}'

        # Registrar en sl_orders
        await supabase.table('sl_orders').insert({
            'position_id':      position_id,
            'symbol':           symbol,
            'side':             sl_side,
            'sl_type':          'dynamic',
            'sl_price':         sl_price,
            'exchange_order_id': exchange_id,
            'status':           'active',
        }).execute()

        # Actualizar position con el ID
        await supabase.table('positions')\
            .update({
                'sl_exchange_order_id': exchange_id
            })\
            .eq('id', position_id)\
            .execute()

        log_info('SL_MANAGER',
            f'SL enviado al exchange: '
            f'{symbol} @ {sl_price:.6f} '
            f'ID: {exchange_id}'
        )
        return exchange_id

    except Exception as e:
        log_error('SL_MANAGER',
            f'Error enviando SL al exchange: {e}'
        )
        return None


async def cancel_all_sl_orders(
    symbol:      str,
    position:    dict,
    supabase,
    reason:      str = 'position_closed'
):
    """
    Cancela TODAS las órdenes SL activas del exchange.
    """
    position_id = position.get('id')
    if not position_id:
        return

    # Obtener todas las SL activas
    sl_res = await supabase\
        .table('sl_orders')\
        .select('*')\
        .eq('position_id', position_id)\
        .eq('status', 'active')\
        .execute()

    sl_orders = sl_res.data or []

    for sl_order in sl_orders:
        exchange_id = sl_order.get('exchange_order_id')
        market_type = sl_order.get('market_type', 'crypto_futures')

        try:
            # Cancelar en el exchange
            if exchange_id and \
               not exchange_id.startswith('paper') and \
               not exchange_id.startswith('ctdr'):

                if market_type == 'crypto_futures':
                    from app.execution.providers.binance_provider import (
                        BinanceCryptoProvider
                    )
                    provider = BinanceCryptoProvider()
                    # We might need await or proper instantiation depending on provider
                    await provider.cancel_order(
                        symbol   = symbol,
                        order_id = exchange_id,
                    )

            # Actualizar en Supabase
            await supabase\
                .table('sl_orders')\
                .update({
                    'status':       'cancelled',
                    'cancel_reason': reason,
                    'cancelled_at': datetime.now(
                        timezone.utc
                    ).isoformat(),
                })\
                .eq('id', sl_order['id'])\
                .execute()

            log_info('SL_MANAGER',
                f'SL cancelado: {symbol} '
                f'ID={exchange_id} '
                f'razón={reason}'
            )

        except Exception as e:
            log_error('SL_MANAGER',
                f'Error cancelando SL '
                f'{exchange_id}: {e}'
            )

    # Limpiar en la posición
    await supabase.table('positions')\
        .update({
            'sl_exchange_order_id': None,
            'sl_dynamic_price':     None,
        })\
        .eq('id', position_id)\
        .execute()
