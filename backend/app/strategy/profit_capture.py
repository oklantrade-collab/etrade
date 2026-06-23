"""
MÓDULO A — Profit Capture (Salida por Sobreextensión)

Detecta cuando el precio está en zona de
agotamiento extremo y cierra maximizando
la ganancia. Opcionalmente abre posición
inversa (FLIP) si hay doble confirmación.

Condiciones de salida LONG (sobreextensión):
  C1: RSI >= 75 Y RSI cayendo (ya no sube más)
  C2: High >= upper_6 (techo Fibonacci)
  C3: Open > BB_upper AND Close > Open
      (vela alcista abriendo sobre Bollinger)

Condiciones de salida SHORT (sobreextensión):
  C1: RSI <= 25 Y RSI subiendo
  C2: Low <= lower_6 (fondo Fibonacci)
  C3: Open < BB_lower AND Close < Open
      (vela bajista abriendo bajo Bollinger)

FLIP (cerrar + abrir inversa):
  Solo si se cumplen >= 2 condiciones
  Con 1 sola condición → solo cerrar
"""

import pandas as pd
from datetime import datetime, timezone
from app.core.logger import log_info


# ── Configuración ─────────────────────────────
CAPTURE_CONFIG = {
    'crypto_futures': {
        'rsi_overbought_long':  75,
        'rsi_oversold_short':   25,
        'rsi_must_be_turning':  True,
        # RSI debe estar girando (no solo tocar)
        'rsi_turning_lookback': 2,
        # velas para confirmar giro del RSI
        'min_conditions_to_close': 1,
        # mínimo de condiciones para cerrar
        'min_conditions_to_flip':  2,
        # mínimo para hacer FLIP
        'bb_body_min_pct':      0.30,
        # cuerpo mínimo de la vela BB
        'bb_invalid_width_pct': 0.005,
        # ancho BB < 0.5% = inválido
        'min_pnl_pct':          0.00,
    },
    'forex_futures': {
        'rsi_overbought_long':  80,
        'rsi_oversold_short':   20,
        'rsi_must_be_turning':  True,
        'rsi_turning_lookback': 2,
        'min_conditions_to_close': 1,
        'min_conditions_to_flip':  2,
        'bb_body_min_pct':      0.30,
        'bb_invalid_width_pct': 0.003,
        'min_pnl_pct':          0.15,
    },
    'stocks_spot': {
        'rsi_overbought_long':  75,
        'rsi_oversold_short':   25,
        'rsi_must_be_turning':  True,
        'rsi_turning_lookback': 2,
        'min_conditions_to_close': 1,
        'min_conditions_to_flip':  2,
        # Stocks NO hacen FLIP (no hay SHORT directo)
        'allow_flip':           False,
        'bb_body_min_pct':      0.30,
        'bb_invalid_width_pct': 0.005,
    },
}


def check_rsi_exhaustion(
    snap:        dict,
    df_15m:      pd.DataFrame,
    side:        str,
    market_type: str = 'crypto_futures',
) -> dict:
    """
    Verifica si el RSI indica sobreextensión
    Y si ya está girando (peak confirmado).

    Para LONG:
      RSI >= 75 AND RSI_actual < RSI_prev
      (ya superó el pico y está bajando)

    Para SHORT:
      RSI <= 25 AND RSI_actual > RSI_prev
      (ya tocó el fondo y está subiendo)
    """
    cfg        = CAPTURE_CONFIG.get(market_type, {})
    rsi_now    = float(snap.get('rsi_14', 50))
    must_turn  = bool(cfg.get('rsi_must_be_turning', True))
    is_long    = side in ('long', 'buy')

    overbought = int(cfg.get('rsi_overbought_long', 75))
    oversold   = int(cfg.get('rsi_oversold_short', 25))

    # Verificar nivel de RSI
    if is_long:
        level_ok = rsi_now >= overbought
    else:
        level_ok = rsi_now <= oversold

    if not level_ok:
        return {
            'triggered': False,
            'rsi':       rsi_now,
            'reason':    f'RSI={rsi_now:.1f} no en zona extrema',
        }

    # Verificar giro del RSI
    is_turning = False
    if must_turn and df_15m is not None \
       and len(df_15m) >= 3:
        # Calcular RSI de las últimas velas
        # (simplificado: usar columna rsi si existe
        #  o comparar con snap anterior)
        rsi_prev = float(
            snap.get('rsi_14_prev', rsi_now)
        )
        if is_long:
            # Para LONG: RSI debe estar bajando
            is_turning = rsi_now < rsi_prev
        else:
            # Para SHORT: RSI debe estar subiendo
            is_turning = rsi_now > rsi_prev

    triggered = level_ok and (
        is_turning or not must_turn
    )

    return {
        'triggered': triggered,
        'rsi':       rsi_now,
        'turning':   is_turning,
        'threshold': overbought if is_long else oversold,
        'reason': (
            f'RSI={rsi_now:.1f} '
            f'{"≥" if is_long else "≤"} '
            f'{overbought if is_long else oversold}'
            + (' y girando ✅' if is_turning else
               ' pero sin giro ⚠️')
        ),
    }


def check_fibonacci_extreme(
    snap:  dict,
    df_15m: pd.DataFrame,
    side:  str,
) -> dict:
    """
    Verifica si el precio tocó la banda
    Fibonacci extrema (upper_6 para LONG,
    lower_6 para SHORT).

    Condición: HIGH >= upper_6 (LONG)
               LOW <= lower_6 (SHORT)
    """
    is_long = side in ('long', 'buy')

    if is_long:
        upper_6 = float(snap.get('upper_6', 0))
        if upper_6 <= 0:
            return {
                'triggered': False,
                'reason':    'upper_6 no disponible',
            }
        # Usar el high de la última vela cerrada
        high = 0.0
        if df_15m is not None and len(df_15m) >= 2:
            high = float(
                df_15m.iloc[-2].get('high', 0)
            )
        if high <= 0:
            high = float(snap.get('price', 0))

        triggered = high >= upper_6
        return {
            'triggered':  triggered,
            'high':       high,
            'upper_6':    upper_6,
            'reason': (
                f'High={high:.5f} '
                f'{"≥" if triggered else "<"} '
                f'upper_6={upper_6:.5f}'
            ),
        }

    else:
        lower_6 = float(snap.get('lower_6', 0))
        if lower_6 <= 0:
            return {
                'triggered': False,
                'reason':    'lower_6 no disponible',
            }
        low = 0.0
        if df_15m is not None and len(df_15m) >= 2:
            low = float(
                df_15m.iloc[-2].get('low', 0)
            )
        if low <= 0:
            low = float(snap.get('price', 0))

        triggered = low <= lower_6
        return {
            'triggered':  triggered,
            'low':        low,
            'lower_6':    lower_6,
            'reason': (
                f'Low={low:.5f} '
                f'{"≤" if triggered else ">"} '
                f'lower_6={lower_6:.5f}'
            ),
        }


def check_bollinger_breakout(
    snap:        dict,
    df_15m:      pd.DataFrame,
    side:        str,
    market_type: str = 'crypto_futures',
) -> dict:
    """
    Verifica si hay un Breakout sobre el
    Bollinger Band con vela confirmada.

    Para LONG:
      Open > BB_upper AND Close > Open
      (vela alcista abriendo sobre el Bollinger)

    Para SHORT:
      Open < BB_lower AND Close < Open
      (vela bajista abriendo bajo el Bollinger)

    También detecta si el Bollinger es inválido
    (muy estrecho = baja volatilidad).
    """
    cfg     = CAPTURE_CONFIG.get(market_type, {})
    is_long = side in ('long', 'buy')

    bb_upper = float(snap.get(
        'bb_upper',
        snap.get('upper_bollinger', 0)
    ))
    bb_lower = float(snap.get(
        'bb_lower',
        snap.get('lower_bollinger', 0)
    ))
    price    = float(snap.get('price', 0))

    # Verificar si el Bollinger es válido
    bb_width_pct = 0.0
    bb_invalid   = False
    if bb_upper > 0 and bb_lower > 0 and price > 0:
        bb_width     = bb_upper - bb_lower
        bb_width_pct = bb_width / price * 100
        min_width    = float(
            cfg.get('bb_invalid_width_pct', 0.005)
        ) * 100
        bb_invalid   = bb_width_pct < min_width

    # Verificar vela de breakout
    triggered   = False
    vela_reason = 'Sin datos de vela'

    if df_15m is not None and len(df_15m) >= 2:
        last = df_15m.iloc[-2]
        o    = float(last.get('open',  0))
        c    = float(last.get('close', 0))
        h    = float(last.get('high',  0))
        l    = float(last.get('low',   0))

        if h > l and o > 0:
            body_pct = abs(c - o) / (h - l)
            body_min = float(
                cfg.get('bb_body_min_pct', 0.30)
            )

            if is_long and bb_upper > 0:
                bb_breakout = (
                    o > bb_upper and
                    c > o and
                    body_pct >= body_min
                )
                vela_reason = (
                    f'Open({o:.5f}) '
                    f'{">" if bb_breakout else "<="} '
                    f'BB_upper({bb_upper:.5f}), '
                    f'Close({c:.5f}) '
                    f'{">" if c>o else "<="} '
                    f'Open, body={body_pct*100:.1f}%'
                )
                triggered = bb_breakout

            elif not is_long and bb_lower > 0:
                bb_breakout = (
                    o < bb_lower and
                    c < o and
                    body_pct >= body_min
                )
                vela_reason = (
                    f'Open({o:.5f}) '
                    f'{"<" if bb_breakout else ">="} '
                    f'BB_lower({bb_lower:.5f}), '
                    f'Close({c:.5f}) '
                    f'{"<" if c<o else ">="} '
                    f'Open, body={body_pct*100:.1f}%'
                )
                triggered = bb_breakout

    return {
        'triggered':   triggered,
        'bb_upper':    bb_upper,
        'bb_lower':    bb_lower,
        'bb_width_pct': round(bb_width_pct, 4),
        'bb_invalid':  bb_invalid,
        'reason':      vela_reason,
    }


def check_extreme_structure_fx(snap: dict, df_15m: pd.DataFrame, side: str) -> dict:
    """
    Verifica si hay una extensión doble (Bollinger + Fibonacci) específica para Forex.
    SHORT: CLOSE <= BB_LOWER AND LOW <= LOWER_6
    LONG:  CLOSE >= BB_UPPER AND HIGH >= UPPER_6
    """
    is_long = side in ('long', 'buy')
    bb_upper = float(snap.get('bb_upper', snap.get('upper_bollinger', 0)))
    bb_lower = float(snap.get('bb_lower', snap.get('lower_bollinger', 0)))
    
    triggered = False
    vela_reason = 'Sin datos de vela'

    if df_15m is not None and len(df_15m) >= 2:
        last = df_15m.iloc[-2]
        c = float(last.get('close', 0))
        h = float(last.get('high', 0))
        l = float(last.get('low', 0))
        
        if c > 0:
            if is_long:
                upper_6 = float(snap.get('upper_6', 0))
                if upper_6 > 0 and bb_upper > 0:
                    triggered = (c >= bb_upper) and (h >= upper_6)
                    vela_reason = f'Close({c:.5f}) >= BB_up({bb_upper:.5f}) AND High({h:.5f}) >= U6({upper_6:.5f})'
                else:
                    vela_reason = 'upper_6 o bb_upper no disponibles'
            else:
                lower_6 = float(snap.get('lower_6', 0))
                if lower_6 > 0 and bb_lower > 0:
                    triggered = (c <= bb_lower) and (l <= lower_6)
                    vela_reason = f'Close({c:.5f}) <= BB_low({bb_lower:.5f}) AND Low({l:.5f}) <= L6({lower_6:.5f})'
                else:
                    vela_reason = 'lower_6 o bb_lower no disponibles'

    return {
        'triggered': triggered,
        'reason': vela_reason,
    }


def evaluate_profit_capture(
    symbol:      str,
    side:        str,
    position:    dict,
    current_price: float,
    snap:        dict,
    df_15m:      pd.DataFrame,
    market_type: str = 'crypto_futures',
) -> dict:
    """
    Función principal del MÓDULO A.

    Evalúa las 3 condiciones de sobreextensión
    y determina si cerrar y/o flipear.

    Retorna:
      action:  'close' | 'flip' | 'hold'
      conditions_met: int
      flip_direction: str
      triggered_by:   list
    """
    cfg          = CAPTURE_CONFIG.get(market_type, {})
    min_close    = int(
        cfg.get('min_conditions_to_close', 1)
    )
    min_flip     = int(
        cfg.get('min_conditions_to_flip', 2)
    )
    allow_flip   = bool(cfg.get('allow_flip', True))
    is_long      = side in ('long', 'buy')

    # ── Verificar ganancia mínima ──────────────
    min_pnl = float(cfg.get('min_pnl_pct', 0.0))
    entry  = float(position.get(
        'avg_entry_price',
        position.get('entry_price',
                     position.get('avg_price', 0))
    ))
    if entry > 0:
        if is_long:
            pnl_pct = (current_price - entry) / entry * 100
        else:
            pnl_pct = (entry - current_price) / entry * 100
    else:
        pnl_pct = 0

    # No cerrar si la ganancia es menor al mínimo exigido
    # (este módulo es para MAXIMIZAR ganancias en extremos)
    if pnl_pct <= min_pnl:
        return {
            'action':  'hold',
            'pnl_pct': round(pnl_pct, 3),
            'reason':  f'Ganancia ({pnl_pct:.2f}%) no supera el mínimo exigido ({min_pnl}%) — hold',
        }

    # ── Evaluar las condiciones ──────────────
    c1_rsi = check_rsi_exhaustion(
        snap, df_15m, side, market_type
    )
    
    if market_type == 'forex_futures':
        c4_struct = check_extreme_structure_fx(snap, df_15m, side)
        conditions = {
            'C1_rsi':        c1_rsi,
            'C4_structure':  c4_struct,
        }
        triggered_list = []
        if c1_rsi['triggered']:
            triggered_list.append('rsi_exhaustion')
        if c4_struct['triggered']:
            triggered_list.append('extreme_structure')
    else:
        c2_fib = check_fibonacci_extreme(
            snap, df_15m, side
        )
        c3_bb  = check_bollinger_breakout(
            snap, df_15m, side, market_type
        )
        conditions = {
            'C1_rsi':        c1_rsi,
            'C2_fibonacci':  c2_fib,
            'C3_bollinger':  c3_bb,
        }
        triggered_list = []
        if c1_rsi['triggered']:
            triggered_list.append('rsi_exhaustion')
        if c2_fib['triggered']:
            triggered_list.append('fib_extreme')
        if c3_bb['triggered']:
            triggered_list.append('bb_breakout')

    n_triggered = len(triggered_list)

    # ── Determinar acción ─────────────────────
    if n_triggered == 0:
        return {
            'action':         'hold',
            'conditions_met': 0,
            'pnl_pct':        round(pnl_pct, 3),
            'conditions':     conditions,
            'reason': (
                f'0/3 condiciones — mantener. '
                f'PnL=+{pnl_pct:.2f}%'
            ),
        }

    if n_triggered >= min_flip and allow_flip:
        flip_dir = 'sell' if is_long else 'buy'
        action   = 'flip'
    elif n_triggered >= min_close:
        action   = 'close'
        flip_dir = None
    else:
        action   = 'hold'
        flip_dir = None

    log_info('PROFIT_CAPTURE',
        f'{"🔄 FLIP" if action=="flip" else "💰 CLOSE" if action=="close" else "⏳ HOLD"} '
        f'[{symbol}]: {n_triggered}/3 condiciones. '
        f'PnL=+{pnl_pct:.2f}%'
    )

    return {
        'action':          action,
        'conditions_met':  n_triggered,
        'triggered_by':    triggered_list,
        'flip_direction':  flip_dir if action == 'flip' else None,
        'pnl_pct':         round(pnl_pct, 3),
        'conditions':      conditions,
        'reason': (
            f'{n_triggered}/3 condiciones: '
            f'{", ".join(triggered_list)}. '
            f'PnL=+{pnl_pct:.2f}%'
        ),
    }
