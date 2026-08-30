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
                    c > bb_upper and
                    c > o and
                    body_pct >= body_min
                )
                vela_reason = (
                    f'Close({c:.5f}) '
                    f'{">" if bb_breakout else "<="} '
                    f'BB_upper({bb_upper:.5f}), '
                    f'Close({c:.5f}) '
                    f'{">" if c>o else "<="} '
                    f'Open, body={body_pct*100:.1f}%'
                )
                triggered = bb_breakout

            elif not is_long and bb_lower > 0:
                bb_breakout = (
                    c < bb_lower and
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
    
    c2_fib = check_fibonacci_extreme(snap, df_15m, side)
    c3_bb  = check_bollinger_breakout(snap, df_15m, side, market_type)
    
    if market_type == 'forex_futures':
        c4_struct = check_extreme_structure_fx(snap, df_15m, side)
        conditions = {
            'C1_rsi':        c1_rsi,
            'C2_fibonacci':  c2_fib,
            'C3_bollinger':  c3_bb,
            'C4_structure':  c4_struct,
        }
        triggered_list = []
        if c1_rsi['triggered']: triggered_list.append('rsi_exhaustion')
        if c2_fib['triggered']: triggered_list.append('fib_extreme')
        if c3_bb['triggered']:  triggered_list.append('bb_breakout')
        if c4_struct['triggered']: triggered_list.append('extreme_structure')
    else:
        conditions = {
            'C1_rsi':        c1_rsi,
            'C2_fibonacci':  c2_fib,
            'C3_bollinger':  c3_bb,
        }
        triggered_list = []
        if c1_rsi['triggered']: triggered_list.append('rsi_exhaustion')
        if c2_fib['triggered']: triggered_list.append('fib_extreme')
        if c3_bb['triggered']:  triggered_list.append('bb_breakout')

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


def evaluate_mtf_trend_guard(
    side: str,
    df_15m: pd.DataFrame,
    df_5m: pd.DataFrame = None,
    current_price: float = 0.0,
    symbol: str = '',
    market_type: str = 'forex_futures',
    pnl_pips: float = 0.0,
    pnl_pct: float = 0.0,
    max_pnl_pips: float = 0.0,
    max_pnl_pct: float = 0.0
) -> dict:
    """
    Blindaje de Tendencia en 15m y Transición Reactiva a 5m (Anti-Micro-Scalp).
    Aplica para LONGs y SHORTs, en Forex y Crypto.
    
    1. Blindaje 15m:
       - LONG: Si EMA3_15m > EMA9_15m y Slope > 0 -> Bloquea salida prematura.
       - SHORT: Si EMA3_15m < EMA9_15m y Slope < 0 -> Bloquea salida prematura.
    2. Transición 5m:
       - Si la pendiente en 15m se aplana/invierte:
         * LONG: Salida autorizada SOLO si EMA3_5m < EMA9_5m Y Precio < EMA20_5m.
         * SHORT: Salida autorizada SOLO si EMA3_5m > EMA9_5m Y Precio > EMA20_5m.
    3. Anti-Giveback:
       - Si superó +8 pips (+0.50% en crypto) y cae a +3 pips (+0.20%), asegura salida con ganancia.
    """
    if df_15m is None or len(df_15m) < 15:
        return {'should_block': False, 'reason': 'Datos 15m insuficientes'}
    
    try:
        is_long = side.lower() in ('long', 'buy')
        is_crypto = 'crypto' in market_type.lower() or 'USDT' in symbol.upper()
        
        # Calcular EMAs en 15m
        c_15m = df_15m['close']
        ema3_15m_series = c_15m.ewm(span=3, adjust=False).mean()
        ema9_15m_series = c_15m.ewm(span=9, adjust=False).mean()
        
        ema3_15m = float(ema3_15m_series.iloc[-1])
        ema3_15m_prev = float(ema3_15m_series.iloc[-2]) if len(ema3_15m_series) >= 2 else ema3_15m
        ema9_15m = float(ema9_15m_series.iloc[-1])
        
        slope_15m = ema3_15m - ema3_15m_prev
        
        # ── 1. Anti-Giveback de Seguridad (Si el trade superó +8 pips y retrocede a +3 pips) ──
        high_pnl_pips = max(max_pnl_pips, pnl_pips)
        high_pnl_pct = max(max_pnl_pct, pnl_pct)
        has_reached_high_profit = (high_pnl_pips >= 8.0) if not is_crypto else (high_pnl_pct >= 0.50)
        at_safety_floor = (pnl_pips <= 3.5 and pnl_pips >= 2.0) if not is_crypto else (pnl_pct <= 0.25 and pnl_pct >= 0.15)
        if has_reached_high_profit and at_safety_floor:
            return {
                'should_block': False,
                'reason': f"Anti-Giveback Activado: Asegurando ganancia mínima (+{pnl_pips:.1f}p / +{pnl_pct:.2f}%)"
            }

        # ── 2. Evaluación para LONG ──
        if is_long:
            # Caso 1: Tendencia 15m alcista fuerte (EMA3 > EMA9 y Slope > 0) -> BLINDAJE
            if ema3_15m > ema9_15m and slope_15m > 0:
                return {
                    'should_block': True,
                    'reason': f"Blindaje 15m LONG Activo: EMA3_15m ({ema3_15m:.5f}) > EMA9_15m ({ema9_15m:.5f}) con pendiente positiva. Mantener Runner."
                }
            
            # Caso 2: Pendiente 15m aplanada o negativa -> Transición Reactiva a 5m
            if df_5m is not None and len(df_5m) >= 20:
                c_5m = df_5m['close']
                ema3_5m = float(c_5m.ewm(span=3, adjust=False).mean().iloc[-1])
                ema9_5m = float(c_5m.ewm(span=9, adjust=False).mean().iloc[-1])
                ema20_5m = float(c_5m.ewm(span=20, adjust=False).mean().iloc[-1])
                
                # Quiebre confirmado en 5m: EMA3 < EMA9 Y precio perfora EMA20
                if ema3_5m < ema9_5m and current_price < ema20_5m:
                    return {
                        'should_block': False,
                        'reason': f"Quiebre 5m LONG confirmado (EMA3_5m={ema3_5m:.5f} < EMA9_5m={ema9_5m:.5f} y Precio < EMA20_5m={ema20_5m:.5f}). Salida autorizada."
                    }
                else:
                    return {
                        'should_block': True,
                        'reason': f"Transición 5m LONG: Pendiente 15m aplanada pero microestructura 5m sobre EMA20 ({ema20_5m:.5f}). Mantener posición."
                    }

        # ── 3. Evaluación para SHORT ──
        else:
            # Caso 1: Tendencia 15m bajista fuerte (EMA3 < EMA9 y Slope < 0) -> BLINDAJE
            if ema3_15m < ema9_15m and slope_15m < 0:
                return {
                    'should_block': True,
                    'reason': f"Blindaje 15m SHORT Activo: EMA3_15m ({ema3_15m:.5f}) < EMA9_15m ({ema9_15m:.5f}) con pendiente negativa. Mantener Runner."
                }
            
            # Caso 2: Pendiente 15m aplanada o positiva -> Transición Reactiva a 5m
            if df_5m is not None and len(df_5m) >= 20:
                c_5m = df_5m['close']
                ema3_5m = float(c_5m.ewm(span=3, adjust=False).mean().iloc[-1])
                ema9_5m = float(c_5m.ewm(span=9, adjust=False).mean().iloc[-1])
                ema20_5m = float(c_5m.ewm(span=20, adjust=False).mean().iloc[-1])
                
                # Quiebre confirmado en 5m: EMA3 > EMA9 Y precio supera EMA20
                if ema3_5m > ema9_5m and current_price > ema20_5m:
                    return {
                        'should_block': False,
                        'reason': f"Quiebre 5m SHORT confirmado (EMA3_5m={ema3_5m:.5f} > EMA9_5m={ema9_5m:.5f} y Precio > EMA20_5m={ema20_5m:.5f}). Salida autorizada."
                    }
                else:
                    return {
                        'should_block': True,
                        'reason': f"Transición 5m SHORT: Pendiente 15m aplanada pero microestructura 5m bajo EMA20 ({ema20_5m:.5f}). Mantener posición."
                    }

        return {'should_block': False, 'reason': 'Sin bloqueo activo'}
    except Exception as e:
        return {'should_block': False, 'reason': f"Error en MTF Trend Guard: {e}"}


def evaluate_dynamic_tp_v6(
    symbol: str,
    side: str,
    current_price: float,
    entry_price: float,
    df_15m: pd.DataFrame,
    df_5m: pd.DataFrame = None,
    snap: dict = None,
    max_pnl_pips: float = 0.0,
    max_pnl_pct: float = 0.0,
    partial_already_taken: bool = False,
    market_type: str = 'forex_futures',
) -> dict:
    """
    Sistema Dinámico de Take Profit v6 (Unificado Forex y Crypto).
    
    Evalúa 5 reglas técnicas cuantitativas en 15m:
    1. Clímax RSI de 2 Niveles (Extremo < 15 / > 85 o Giro en Sobreventa <= 22 / Sobrecompra >= 78).
    2. Clímax Fibonacci (Toque L5/U5 o Falla en L4/U4).
    3. Reversión SIPV tras Cascada de Medias (EMA3 vs EMA9 vs EMA20 con cierre opuesto a EMA3).
    4. Guarda Anti-Giveback (Protección del 70% de ganancia máxima alcanzada tras +20 pips / +1.0%).
    5. Scale-Out 50/50 (Toma parcial del 50% al alcanzar L4/U4 por primera vez).
    
    Retorna diccionario estructurado con la decisión de salida.
    """
    res_default = {
        'should_close': False,
        'is_partial': False,
        'partial_pct': 0.0,
        'trailing_sl_price': None,
        'reason': 'Trend running - no TP trigger',
        'rule_code': 'HOLD_TREND'
    }

    if df_15m is None or len(df_15m) < 20 or entry_price <= 0:
        return res_default

    side_norm = side.lower()
    is_long = side_norm in ('long', 'buy')
    snap = snap or {}
    
    # Parámetros por mercado
    is_crypto = 'crypto' in market_type.lower() or 'USDT' in symbol.upper()
    pip_size = 0.01 if ('JPY' in symbol.upper() or 'XAU' in symbol.upper()) else (0.0001 if not is_crypto else 1.0)
    
    # Calcular PnL actual
    if is_long:
        curr_pnl_pips = (current_price - entry_price) / pip_size if not is_crypto else 0.0
        curr_pnl_pct = ((current_price - entry_price) / entry_price) * 100.0
    else:
        curr_pnl_pips = (entry_price - current_price) / pip_size if not is_crypto else 0.0
        curr_pnl_pct = ((entry_price - current_price) / entry_price) * 100.0

    # 🛡️ Blindaje de Take Profit: No activar salidas de toma de ganancias si la posición está en pérdida o breakeven
    is_in_profit = (curr_pnl_pct > 0.05) if is_crypto else (curr_pnl_pips >= 1.0)
    if not is_in_profit:
        return res_default

    # Extraer indicadores de 15m
    c0 = df_15m.iloc[-1]
    c1 = df_15m.iloc[-2] if len(df_15m) >= 2 else c0
    
    close0 = float(c0.get('close', c0.get('Close', current_price)))
    open0 = float(c0.get('open', c0.get('Open', close0)))
    high0 = float(c0.get('high', c0.get('High', close0)))
    low0 = float(c0.get('low', c0.get('Low', close0)))
    
    close1 = float(c1.get('close', c1.get('Close', close0)))
    high1 = float(c1.get('high', c1.get('High', high0)))
    low1 = float(c1.get('low', c1.get('Low', low0)))

    # Bollinger Bands 15m
    basis_series = df_15m['close'].rolling(20).mean()
    std_series = df_15m['close'].rolling(20).std()
    
    basis = float(snap.get('basis') or basis_series.iloc[-1])
    std = float(std_series.iloc[-1]) if len(std_series) > 0 and not pd.isna(std_series.iloc[-1]) else 0.0
    
    bb_upper = float(snap.get('upper_1') or snap.get('upper_bollinger') or (basis + 2.0 * std))
    bb_lower = float(snap.get('lower_1') or snap.get('lower_bollinger') or (basis - 2.0 * std))
    
    lower_4 = float(snap.get('lower_4') or (basis - 2.618 * std))
    lower_5 = float(snap.get('lower_5') or (basis - 3.236 * std))
    upper_4 = float(snap.get('upper_4') or (basis + 2.618 * std))
    upper_5 = float(snap.get('upper_5') or (basis + 3.236 * std))
    
    # EMAs 15m
    c_series = df_15m['close']
    ema3_series = c_series.ewm(span=3, adjust=False).mean()
    ema9_series = c_series.ewm(span=9, adjust=False).mean()
    ema20_series = c_series.ewm(span=20, adjust=False).mean()
    
    ema3_0 = float(snap.get('ema3') or ema3_series.iloc[-1])
    ema9_0 = float(snap.get('ema9') or ema9_series.iloc[-1])
    ema20_0 = float(snap.get('ema20') or ema20_series.iloc[-1])
    
    # RSI 15m
    delta = c_series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi_series = 100 - (100 / (1 + rs))
    
    rsi_0 = float(snap.get('rsi_14') or snap.get('rsi') or rsi_series.iloc[-1])
    rsi_1 = float(rsi_series.iloc[-2]) if len(rsi_series) >= 2 else rsi_0

    # ════════════════════════════════════════════════════════════
    # REGLA 4: GUARDA ANTI-GIVEBACK (PROTECCIÓN 70% GANANCIA PICO)
    # ════════════════════════════════════════════════════════════
    peak_threshold_reached = (max_pnl_pips >= 20.0 if not is_crypto else max_pnl_pct >= 1.0)
    if peak_threshold_reached:
        if not is_crypto:
            guaranteed_pips = max_pnl_pips * 0.70
            if is_long:
                trail_sl = entry_price + (guaranteed_pips * pip_size)
                if current_price <= trail_sl and curr_pnl_pips > 0:
                    return {
                        'should_close': True,
                        'is_partial': False,
                        'partial_pct': 0.0,
                        'trailing_sl_price': trail_sl,
                        'reason': f"Anti-Giveback 70% activado (Pico: +{max_pnl_pips:.1f}p -> Asegurado: +{guaranteed_pips:.1f}p)",
                        'rule_code': 'TP_ANTI_GIVEBACK_70'
                    }
            else:
                trail_sl = entry_price - (guaranteed_pips * pip_size)
                if current_price >= trail_sl and curr_pnl_pips > 0:
                    return {
                        'should_close': True,
                        'is_partial': False,
                        'partial_pct': 0.0,
                        'trailing_sl_price': trail_sl,
                        'reason': f"Anti-Giveback 70% activado (Pico: +{max_pnl_pips:.1f}p -> Asegurado: +{guaranteed_pips:.1f}p)",
                        'rule_code': 'TP_ANTI_GIVEBACK_70'
                    }
        else:
            guaranteed_pct = max_pnl_pct * 0.70
            if is_long:
                trail_sl = entry_price * (1.0 + guaranteed_pct / 100.0)
                if current_price <= trail_sl and curr_pnl_pct > 0:
                    return {
                        'should_close': True,
                        'is_partial': False,
                        'partial_pct': 0.0,
                        'trailing_sl_price': trail_sl,
                        'reason': f"Anti-Giveback 70% activado (Pico: +{max_pnl_pct:.2f}% -> Asegurado: +{guaranteed_pct:.2f}%)",
                        'rule_code': 'TP_ANTI_GIVEBACK_70'
                    }
            else:
                trail_sl = entry_price * (1.0 - guaranteed_pct / 100.0)
                if current_price >= trail_sl and curr_pnl_pct > 0:
                    return {
                        'should_close': True,
                        'is_partial': False,
                        'partial_pct': 0.0,
                        'trailing_sl_price': trail_sl,
                        'reason': f"Anti-Giveback 70% activado (Pico: +{max_pnl_pct:.2f}% -> Asegurado: +{guaranteed_pct:.2f}%)",
                        'rule_code': 'TP_ANTI_GIVEBACK_70'
                    }

    # ════════════════════════════════════════════════════════════
    # REGLA 1: CLÍMAX RSI (2 NIVELES)
    # ════════════════════════════════════════════════════════════
    if is_long:
        # Nivel 1: Clímax Absoluto
        if rsi_0 >= 85 and (close0 > bb_upper or current_price > bb_upper):
            return {
                'should_close': True,
                'is_partial': False,
                'partial_pct': 0.0,
                'trailing_sl_price': None,
                'reason': f"Clímax RSI Extremo LONG ({rsi_0:.1f} >= 85) con ruptura de BB superior",
                'rule_code': 'TP_RSI_CLIMAX_EXTREME'
            }
        # Nivel 2: Giro en Sobrecompra
        if rsi_0 >= 78 and rsi_0 < rsi_1 and close0 < open0:
            return {
                'should_close': True,
                'is_partial': False,
                'partial_pct': 0.0,
                'trailing_sl_price': None,
                'reason': f"Giro en Sobrecompra LONG (RSI={rsi_0:.1f} < prev={rsi_1:.1f}) con vela roja",
                'rule_code': 'TP_RSI_TURNAROUND'
            }
    else:
        # Nivel 1: Clímax Absoluto
        if rsi_0 <= 15 and (close0 < bb_lower or current_price < bb_lower):
            return {
                'should_close': True,
                'is_partial': False,
                'partial_pct': 0.0,
                'trailing_sl_price': None,
                'reason': f"Clímax RSI Extremo SHORT ({rsi_0:.1f} <= 15) con ruptura de BB inferior",
                'rule_code': 'TP_RSI_CLIMAX_EXTREME'
            }
        # Nivel 2: Giro en Sobreventa
        if rsi_0 <= 22 and rsi_0 > rsi_1 and close0 > open0:
            return {
                'should_close': True,
                'is_partial': False,
                'partial_pct': 0.0,
                'trailing_sl_price': None,
                'reason': f"Giro en Sobreventa SHORT (RSI={rsi_0:.1f} > prev={rsi_1:.1f}) con vela verde",
                'rule_code': 'TP_RSI_TURNAROUND'
            }

    # ════════════════════════════════════════════════════════════
    # REGLA 2: CLÍMAX FIBONACCI (LOWER_5/UPPER_5 Y FALLA L4/U4)
    # ════════════════════════════════════════════════════════════
    if is_long:
        if upper_5 > 0 and (current_price >= upper_5 or high0 >= upper_5) and (close0 > bb_upper or current_price > bb_upper):
            return {
                'should_close': True,
                'is_partial': False,
                'partial_pct': 0.0,
                'trailing_sl_price': None,
                'reason': f"Clímax Fibonacci UPPER_5 alcanzado ({max(high0, current_price):.5f} >= {upper_5:.5f})",
                'rule_code': 'TP_FIB_U5_CLIMAX'
            }
        if upper_4 > 0 and high1 >= upper_4 and high0 < high1 and close0 < open0:
            # Validar con MTF Trend Guard antes de cerrar
            guard = evaluate_mtf_trend_guard('long', df_15m, df_5m, current_price, symbol, market_type, curr_pnl_pips, curr_pnl_pct)
            if not guard['should_block']:
                return {
                    'should_close': True,
                    'is_partial': False,
                    'partial_pct': 0.0,
                    'trailing_sl_price': None,
                    'reason': f"Falla de nuevo máximo en UPPER_4 Fibonacci ({high0:.5f} < prev={high1:.5f}) | {guard.get('reason')}",
                    'rule_code': 'TP_FIB_U4_EXHAUSTION'
                }
    else:
        if lower_5 > 0 and (current_price <= lower_5 or low0 <= lower_5) and (close0 < bb_lower or current_price < bb_lower):
            return {
                'should_close': True,
                'is_partial': False,
                'partial_pct': 0.0,
                'trailing_sl_price': None,
                'reason': f"Clímax Fibonacci LOWER_5 alcanzado ({min(low0, current_price):.5f} <= {lower_5:.5f})",
                'rule_code': 'TP_FIB_L5_CLIMAX'
            }
        if lower_4 > 0 and low1 <= lower_4 and low0 > low1 and close0 > open0:
            # Validar con MTF Trend Guard antes de cerrar
            guard = evaluate_mtf_trend_guard('short', df_15m, df_5m, current_price, symbol, market_type, curr_pnl_pips, curr_pnl_pct)
            if not guard['should_block']:
                return {
                    'should_close': True,
                    'is_partial': False,
                    'partial_pct': 0.0,
                    'trailing_sl_price': None,
                    'reason': f"Falla de nuevo mínimo en LOWER_4 Fibonacci ({low0:.5f} > prev={low1:.5f}) | {guard.get('reason')}",
                    'rule_code': 'TP_FIB_L4_EXHAUSTION'
                }

    # ════════════════════════════════════════════════════════════
    # REGLA 3: REVERSIÓN SIPV TRAS CASCADA DE MEDIAS (CON BLINDAJE MTF)
    # ════════════════════════════════════════════════════════════
    if is_long:
        dist_ema_long = (ema3_0 - ema9_0) / pip_size if not is_crypto else ((ema3_0 - ema9_0) / ema9_0 * 100.0)
        is_cascade_long = (ema3_0 > ema9_0 > ema20_0) or (dist_ema_long >= (3.0 if not is_crypto else 0.25))
        if is_cascade_long and close0 < ema3_0 and (close0 < open0 or close0 < close1):
            guard = evaluate_mtf_trend_guard('long', df_15m, df_5m, current_price, symbol, market_type, curr_pnl_pips, curr_pnl_pct)
            if not guard['should_block']:
                return {
                    'should_close': True,
                    'is_partial': False,
                    'partial_pct': 0.0,
                    'trailing_sl_price': None,
                    'reason': f"Reversión SIPV LONG confirmada (Close={close0:.5f} < EMA3={ema3_0:.5f}) | {guard.get('reason')}",
                    'rule_code': 'TP_SIPV_REVERSAL'
                }
    else:
        dist_ema_short = (ema9_0 - ema3_0) / pip_size if not is_crypto else ((ema9_0 - ema3_0) / ema3_0 * 100.0)
        is_cascade_short = (ema3_0 < ema9_0 < ema20_0) or (dist_ema_short >= (3.0 if not is_crypto else 0.25))
        if is_cascade_short and close0 > ema3_0 and (close0 > open0 or close0 > close1):
            guard = evaluate_mtf_trend_guard('short', df_15m, df_5m, current_price, symbol, market_type, curr_pnl_pips, curr_pnl_pct)
            if not guard['should_block']:
                return {
                    'should_close': True,
                    'is_partial': False,
                    'partial_pct': 0.0,
                    'trailing_sl_price': None,
                    'reason': f"Reversión SIPV SHORT confirmada (Close={close0:.5f} > EMA3={ema3_0:.5f}) | {guard.get('reason')}",
                    'rule_code': 'TP_SIPV_REVERSAL'
                }

    # ════════════════════════════════════════════════════════════
    # REGLA 5: SCALE-OUT 50/50 (TOMA PARCIAL AL ALCANZAR L4/U4)
    # ════════════════════════════════════════════════════════════
    if not partial_already_taken:
        if is_long and upper_4 > 0 and (current_price >= upper_4 or high0 >= upper_4):
            return {
                'should_close': True,
                'is_partial': True,
                'partial_pct': 0.50,
                'trailing_sl_price': ema9_0,
                'reason': f"Scale-Out 50% al alcanzar UPPER_4 Fibonacci ({high0:.5f} >= {upper_4:.5f})",
                'rule_code': 'TP_SCALE_OUT_U4'
            }
        elif not is_long and lower_4 > 0 and (current_price <= lower_4 or low0 <= lower_4):
            return {
                'should_close': True,
                'is_partial': True,
                'partial_pct': 0.50,
                'trailing_sl_price': ema9_0,
                'reason': f"Scale-Out 50% al alcanzar LOWER_4 Fibonacci ({low0:.5f} <= {lower_4:.5f})",
                'rule_code': 'TP_SCALE_OUT_L4'
            }

    return res_default
