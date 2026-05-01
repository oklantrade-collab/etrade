"""
Stop Loss Adaptativo para STOCKS.

Sistema de 3 zonas:
  Verde    (0% a -sl_close_threshold):
    Monitoreo normal. Sin acción especial.

  Amarilla (-close_threshold a -wait_threshold):
    Modo Advertencia. Evaluar señales de rebote.
    Si hay señales → esperar.
    Si no hay señales → preparar cierre.

  Roja     (> -wait_threshold):
    Modo Espera. Buscar el mejor momento
    para cerrar con pérdida mínima.
    Nunca cerrar si hay señales de rebote.
    Cerrar forzosamente si supera hard_max
    o si se acaban los días de espera.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from app.core.logger import log_info, log_error, log_warning
from app.stocks.stocks_adaptive_tp import (
    calculate_macro_score,
    fetch_macro_data,
)

# ── Defaults (se sobreescriben con Settings) ──
DEFAULT_CONFIG = {
    'sl_close_threshold':          2.0,
    'sl_wait_threshold':           5.0,
    'sl_max_wait_days':            5,
    'sl_support_band':             'lower_2',
    'sl_recovery_min_pct':         1.0,
    'sl_volume_climax_enabled':    True,
    'sl_macro_enabled':            True,
    'sl_require_candle_confirmation': True,
    'sl_bounce_signals_required':  2,
    'sl_max_loss_hard':            12.0,
}

# Patrones de vela de REBOTE (alcistas)
BOUNCE_PATTERNS = [
    'hammer',
    'bullish_engulfing',
    'doji_dragonfly',
    'morning_star',
    'bullish_harami',
    'piercing_line',
    'tweezer_bottom',
]


# ═══════════════════════════════════════════
# MÓDULO 1 — CARGAR CONFIGURACIÓN DE SETTINGS
# ═══════════════════════════════════════════

async def load_sl_config(supabase) -> dict:
    """
    Carga la configuración de SL desde
    stocks_config en Supabase.
    """
    try:
        res = supabase\
            .table('stocks_config')\
            .select('key,value')\
            .eq('category', 'stop_loss')\
            .execute()

        cfg = dict(DEFAULT_CONFIG)
        for row in (res.data or []):
            key = row['key']
            val = row['value']
            if key in cfg:
                # Convertir al tipo correcto
                if isinstance(cfg[key], bool):
                    cfg[key] = str(val).lower() == 'true'
                elif isinstance(cfg[key], int):
                    cfg[key] = int(float(val))
                elif isinstance(cfg[key], float):
                    cfg[key] = float(val)
                else:
                    cfg[key] = val
        return cfg

    except Exception as e:
        log_error('ADAPTIVE_SL',
            f'Error cargando config: {e}'
        )
        return dict(DEFAULT_CONFIG)


# ═══════════════════════════════════════════
# MÓDULO 2 — DETECTOR DE SEÑALES DE REBOTE
# ═══════════════════════════════════════════

def detect_bounce_candle(
    df:        pd.DataFrame,
    timeframe: str = '15m',
) -> dict:
    """
    Detecta patrones de vela de REBOTE
    (opuesto al detect_exhaustion_candle).
    """
    if df is None or len(df) < 3:
        return {
            'detected': False,
            'pattern':  None,
            'strength': 0,
        }

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    prev2 = df.iloc[-3]

    o  = float(last.get('open',  0))
    h  = float(last.get('high',  0))
    l  = float(last.get('low',   0))
    c  = float(last.get('close', 0))

    if h == l:
        return {
            'detected': False,
            'pattern':  None,
            'strength': 0
        }

    total_range  = h - l
    body_size    = abs(c - o)
    body_pct     = body_size / total_range
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    lower_pct    = lower_shadow / total_range
    upper_pct    = upper_shadow / total_range

    patterns_found = []

    # ── Hammer ────────────────────────────────
    if (lower_pct >= 0.60 and
        body_pct  <= 0.30 and
        upper_pct <= 0.10 and
        c >= o):
        patterns_found.append({
            'name':     'hammer',
            'strength': 8,
            'reason': (
                'Hammer: sombra inferior larga '
                'en zona de soporte'
            )
        })

    # ── Doji Dragonfly ────────────────────────
    if (lower_pct >= 0.70 and
        body_pct  <= 0.10 and
        upper_pct <= 0.10):
        patterns_found.append({
            'name':     'doji_dragonfly',
            'strength': 7,
            'reason': (
                'Doji Dragonfly: rechazo '
                'de precios bajos'
            )
        })

    # ── Bullish Engulfing ─────────────────────
    po = float(prev.get('open',  0))
    pc = float(prev.get('close', 0))
    if (c > o and          # vela actual alcista
        pc < po and        # vela previa bajista
        o <= pc and        # abre <= cierre previo
        c >= po):          # cierra >= apertura previa
        patterns_found.append({
            'name':     'bullish_engulfing',
            'strength': 9,
            'reason': (
                'Bullish Engulfing: '
                'vela alcista envuelve la bajista'
            )
        })

    # ── Morning Star ──────────────────────────
    p2o = float(prev2.get('open',  0))
    p2c = float(prev2.get('close', 0))
    if (p2c < p2o and        # vela 1: bajista
        abs(pc - po) < (     # vela 2: pequeña
            abs(p2c - p2o) * 0.3
        ) and
        c > o and            # vela 3: alcista
        c > (p2o + p2c) / 2):  # cierra > mitad
        patterns_found.append({
            'name':     'morning_star',
            'strength': 9,
            'reason': (
                'Morning Star: patrón '
                'de 3 velas de fondo'
            )
        })

    # ── Piercing Line ─────────────────────────
    if (pc < po and          # previa bajista
        c > o and            # actual alcista
        o < pc and           # abre bajo el cierre previo
        c > (po + pc) / 2):  # cierra > mitad del cuerpo previo
        patterns_found.append({
            'name':     'piercing_line',
            'strength': 7,
            'reason': (
                'Piercing Line: recuperación '
                'de más del 50%'
            )
        })

    # ── Tweezer Bottom ────────────────────────
    pl = float(prev.get('low', 0))
    if (abs(l - pl) / max(l, pl) < 0.002 and
        c > o and
        pc < po):
        patterns_found.append({
            'name':     'tweezer_bottom',
            'strength': 6,
            'reason': (
                'Tweezer Bottom: doble fondo '
                'en mismo nivel'
            )
        })

    if not patterns_found:
        return {
            'detected': False,
            'pattern':  None,
            'strength': 0,
        }

    best = max(
        patterns_found,
        key=lambda x: x['strength']
    )

    return {
        'detected':     True,
        'pattern':      best['name'],
        'strength':     best['strength'],
        'reason':       best['reason'],
        'timeframe':    timeframe,
        'all_patterns': patterns_found,
    }


def detect_volume_climax(
    df:        pd.DataFrame,
    n_candles: int = 10,
) -> dict:
    """
    Detecta el clímax de volumen en la caída.
    """
    if df is None or len(df) < n_candles:
        return {
            'detected': False,
            'reason':   'Datos insuficientes'
        }

    recent = df.tail(n_candles)
    last   = df.iloc[-1]

    vol_last = float(last.get('volume', 0))
    vol_max  = float(recent['volume'].max())
    vol_avg  = float(recent['volume'].mean())

    o = float(last.get('open',  0))
    h = float(last.get('high',  0))
    l = float(last.get('low',   0))
    c = float(last.get('close', 0))

    # ¿Es el mayor volumen del período?
    is_highest_vol = vol_last >= vol_max * 0.95

    # ¿Es una vela bajista?
    is_bearish = c < o

    # ¿El precio cerró en la mitad superior?
    if h > l:
        close_position = (c - l) / (h - l)
        closed_high = close_position >= 0.40
    else:
        closed_high = False

    # ¿El volumen es mucho mayor al promedio?
    vol_ratio = vol_last / vol_avg \
                if vol_avg > 0 else 1.0
    high_vol  = vol_ratio >= 2.0

    climax = (
        is_highest_vol and
        is_bearish and
        closed_high and
        high_vol
    )

    return {
        'detected':   climax,
        'vol_ratio':  round(vol_ratio, 2),
        'vol_last':   vol_last,
        'vol_avg':    vol_avg,
        'is_bearish': is_bearish,
        'closed_high': closed_high,
        'reason': (
            f'Clímax de volumen: '
            f'{vol_ratio:.1f}x el promedio'
            if climax
            else 'Sin clímax de volumen'
        ),
    }


def detect_support_hold(
    current_price: float,
    snap:          dict,
    support_band:  str = 'lower_2',
) -> dict:
    """
    Verifica si el precio está sosteniendo
    sobre la banda de soporte Fibonacci.
    """
    support_price = float(
        snap.get(support_band, 0)
    )

    if support_price <= 0:
        return {
            'holding':       False,
            'support_price': 0,
            'reason':        'Soporte no disponible'
        }

    holding        = current_price > support_price
    distance_pct   = (
        (current_price - support_price)
        / support_price * 100
    )

    if holding and distance_pct < 1.0:
        status = 'testing'
        # Precio muy cerca del soporte
    elif holding:
        status = 'above'
        # Precio claramente sobre el soporte
    else:
        status = 'broken'
        # Soporte roto

    return {
        'holding':       holding,
        'support_price': support_price,
        'support_band':  support_band,
        'distance_pct':  round(distance_pct, 2),
        'status':        status,
        'reason': (
            f'Soporte {support_band} '
            f'${support_price:.2f}: {status} '
            f'(dist={distance_pct:.1f}%)'
        ),
    }


# ═══════════════════════════════════════════
# MÓDULO 3 — SCORE DE REBOTE
# ═══════════════════════════════════════════

def calculate_bounce_score(
    ticker:        str,
    position:      dict,
    current_price: float,
    snap:          dict,
    df_15m:        pd.DataFrame,
    df_5m:         pd.DataFrame = None,
    macro:         dict = None,
    config:        dict = None,
) -> dict:
    """
    Calcula el score de señales de rebote (0-10).
    Cuanto más alto, más probable el rebote.
    """
    cfg        = config or DEFAULT_CONFIG
    score      = 0.0
    components = {}

    # ── C1: Vela de rebote en 15m ─────────────
    if df_15m is not None:
        candle_15m = detect_bounce_candle(
            df_15m, '15m'
        )
        if candle_15m['detected']:
            c1_score = (
                candle_15m['strength'] / 10 * 3.0
            )
            score += c1_score
            components['candle_15m'] = {
                'pattern':   candle_15m['pattern'],
                'strength':  candle_15m['strength'],
                'score_add': c1_score,
            }

    # ── C2: Vela de rebote en 5m ──────────────
    if df_5m is not None:
        candle_5m = detect_bounce_candle(
            df_5m, '5m'
        )
        if candle_5m['detected']:
            c2_score = (
                candle_5m['strength'] / 10 * 2.0
            )
            score += c2_score
            components['candle_5m'] = {
                'pattern':   candle_5m['pattern'],
                'strength':  candle_5m['strength'],
                'score_add': c2_score,
            }

    # ── C3: Clímax de volumen ─────────────────
    if cfg.get('sl_volume_climax_enabled', True) \
       and df_15m is not None:
        climax = detect_volume_climax(df_15m)
        if climax['detected']:
            score += 2.0
            components['volume_climax'] = {
                'vol_ratio': climax['vol_ratio'],
                'score_add': 2.0,
            }

    # ── C4: Soporte Fibonacci aguanta ─────────
    support_band = cfg.get(
        'sl_support_band', 'lower_2'
    )
    support = detect_support_hold(
        current_price, snap, support_band
    )
    if support['holding']:
        if support['status'] == 'above':
            score += 1.5
            components['support'] = {
                'band':      support_band,
                'status':    'holding_above',
                'score_add': 1.5,
            }
        elif support['status'] == 'testing':
            score += 0.8
            components['support'] = {
                'band':      support_band,
                'status':    'testing',
                'score_add': 0.8,
            }
    else:
        # Soporte roto → penalizar
        score -= 1.0
        components['support'] = {
            'band':      support_band,
            'status':    'broken',
            'score_add': -1.0,
        }

    # ── C5: Macro mejorando ───────────────────
    if cfg.get('sl_macro_enabled', True) \
       and macro:
        macro_score = float(
            macro.get('score', 0)
        )
        if macro_score >= 2:
            score += 1.5
            components['macro'] = {
                'score':     macro_score,
                'sentiment': macro.get(
                    'sentiment', ''
                ),
                'score_add': 1.5,
            }
        elif macro_score <= -3:
            score -= 1.0
            components['macro'] = {
                'score':     macro_score,
                'sentiment': 'bearish',
                'score_add': -1.0,
            }

    # Normalizar 0-10
    score = max(0, min(10.0, score))

    signals_required = int(
        cfg.get('sl_bounce_signals_required', 2)
    )
    active_signals = len([
        c for c in components.values()
        if c.get('score_add', 0) > 0
    ])

    # Hay suficientes señales de rebote?
    enough_signals = active_signals >= \
                     signals_required

    if score >= 7:
        recommendation = 'wait_bounce'
        level          = 'strong'
    elif score >= 4 and enough_signals:
        recommendation = 'wait_bounce'
        level          = 'moderate'
    elif score >= 2:
        recommendation = 'monitor'
        level          = 'weak'
    else:
        recommendation = 'close'
        level          = 'none'

    return {
        'score':          round(score, 2),
        'level':          level,
        'recommendation': recommendation,
        'active_signals': active_signals,
        'enough_signals': enough_signals,
        'components':     components,
        'support':        support,
        'reason': (
            f'Rebote {level} '
            f'(score={score:.1f}/10, '
            f'{active_signals} señales): '
            + ', '.join([
                f'{k}={v.get("score_add",0):.1f}'
                for k, v in components.items()
            ])
        ),
    }


# ═══════════════════════════════════════════
# MÓDULO 4 — EVALUACIÓN PRINCIPAL DEL SL
# ═══════════════════════════════════════════

def evaluate_adaptive_sl(
    ticker:        str,
    position:      dict,
    current_price: float,
    snap:          dict,
    df_15m:        pd.DataFrame,
    df_5m:         pd.DataFrame = None,
    macro:         dict = None,
    config:        dict = None,
) -> dict:
    """
    Función principal del SL Adaptativo.
    """
    cfg = config or DEFAULT_CONFIG

    entry_price = float(position.get('avg_price') or position.get('entry_price') or 0)

    if entry_price <= 0:
        return {'action': 'monitor',
                'reason': 'Entry inválido'}

    # Calcular pérdida actual
    loss_pct = (
        (current_price - entry_price)
        / entry_price * 100
    )
    # Para posición LONG: pérdida es negativa

    # Si estamos en ganancia, no evaluar SL adaptativo de pérdida
    if loss_pct >= 0:
        return {
            'action': 'monitor',
            'loss_pct': round(loss_pct, 2),
            'zone': 'green',
            'new_lowest': float(position.get('sl_lowest_price') or current_price),
            'reason': 'En ganancia, sin SL.'
        }

    # Actualizar precio más bajo
    sl_lowest = float(position.get('sl_lowest_price') or current_price)

    # Para long, lowest es el mínimo precio
    new_lowest = min(sl_lowest, current_price) if sl_lowest > 0 else current_price
    lowest_loss_pct = (
        (new_lowest - entry_price)
        / entry_price * 100
    )

    # Recuperación desde el mínimo
    recovery_from_low = (
        (current_price - new_lowest)
        / entry_price * 100
        if new_lowest < current_price
        else 0
    )

    # Thresholds desde config
    close_thr = -float(
        cfg.get('sl_close_threshold', 2.0)
    )
    wait_thr  = -float(
        cfg.get('sl_wait_threshold', 5.0)
    )
    hard_thr  = -float(
        cfg.get('sl_max_loss_hard', 12.0)
    )
    max_days  = int(
        cfg.get('sl_max_wait_days', 5)
    )

    # Verificar tiempo en modo espera
    waiting_since = position.get('sl_waiting_since')
    days_waiting  = 0
    if waiting_since:
        if isinstance(waiting_since, str):
            try:
                waiting_since = datetime.fromisoformat(
                    waiting_since.replace(
                        'Z', '+00:00'
                    )
                )
                days_waiting = (
                    datetime.now(timezone.utc)
                    - waiting_since
                ).days
            except:
                pass

    # ── ZONA VERDE: Sin problema ───────────────
    if loss_pct >= close_thr:
        return {
            'action':          'monitor',
            'loss_pct':        round(loss_pct, 2),
            'zone':            'green',
            'new_lowest':      new_lowest,
            'lowest_loss_pct': round(
                lowest_loss_pct, 2
            ),
            'recovery_from_low': round(
                recovery_from_low, 2
            ),
            'reason': (
                f'Zona verde: pérdida '
                f'{loss_pct:.2f}% '
                f'(< {abs(close_thr):.1f}%)'
            ),
        }

    # ── HARD STOP: Pérdida extrema ─────────────
    if loss_pct <= hard_thr:
        return {
            'action':    'close_forced',
            'loss_pct':  round(loss_pct, 2),
            'zone':      'hard_stop',
            'new_lowest': new_lowest,
            'close_reason': 'hard_stop_exceeded',
            'reason': (
                f'HARD STOP: pérdida '
                f'{loss_pct:.2f}% supera '
                f'el máximo absoluto '
                f'{abs(hard_thr):.1f}%'
            ),
        }

    # ── TIMEOUT: Demasiado tiempo esperando ────
    if days_waiting >= max_days and \
       position.get('sl_mode') == 'waiting':
        return {
            'action':    'close_forced',
            'loss_pct':  round(loss_pct, 2),
            'zone':      'timeout',
            'new_lowest': new_lowest,
            'close_reason': f'timeout_{days_waiting}d',
            'reason': (
                f'TIMEOUT: {days_waiting} días '
                f'en espera (máx={max_days}). '
                f'Pérdida: {loss_pct:.2f}%'
            ),
        }

    # ── CALCULAR SCORE DE REBOTE ───────────────
    bounce = calculate_bounce_score(
        ticker        = ticker,
        position      = position,
        current_price = current_price,
        snap          = snap,
        df_15m        = df_15m,
        df_5m         = df_5m,
        macro         = macro,
        config        = cfg,
    )

    # ── SOPORTE ROTO: cerrar sin importar zona ─
    if not bounce['support']['holding'] and \
       bounce['support']['status'] == 'broken':

        # Solo cerrar si no hay rebote fuerte
        if bounce['score'] < 6:
            return {
                'action':     'close_support_break',
                'loss_pct':   round(loss_pct, 2),
                'zone':       'support_broken',
                'bounce':     bounce,
                'new_lowest': new_lowest,
                'close_reason': 'support_broken',
                'reason': (
                    f'SOPORTE ROTO: '
                    f'{bounce["support"]["support_band"]} '
                    f'= ${bounce["support"]["support_price"]:.2f} '
                    f'sin señales de rebote '
                    f'(bounce score={bounce["score"]:.1f})'
                ),
            }

    # ── ZONA AMARILLA: -close_thr a -wait_thr ──
    if wait_thr < loss_pct < close_thr:
        zone = 'yellow'

        if bounce['recommendation'] == \
           'wait_bounce':
            return {
                'action':     'wait_bounce',
                'loss_pct':   round(loss_pct, 2),
                'zone':       zone,
                'bounce':     bounce,
                'new_lowest': new_lowest,
                'recovery_from_low': round(
                    recovery_from_low, 2
                ),
                'reason': (
                    f'Zona amarilla con rebote '
                    f'({bounce["score"]:.1f}/10): '
                    f'esperar recuperación. '
                    f'Pérdida: {loss_pct:.2f}%'
                ),
            }
        else:
            return {
                'action':       'alert',
                'loss_pct':     round(loss_pct, 2),
                'zone':         zone,
                'bounce':       bounce,
                'new_lowest':   new_lowest,
                'close_reason': 'yellow_no_bounce',
                'reason': (
                    f'Zona amarilla sin rebote '
                    f'({bounce["score"]:.1f}/10). '
                    f'Pérdida: {loss_pct:.2f}%. '
                    f'Preparando cierre...'
                ),
            }

    # ── ZONA ROJA: > -wait_thr ─────────────────
    zone = 'red'

    # Si hay señales de rebote → esperar
    if bounce['recommendation'] == 'wait_bounce':
        return {
            'action':     'wait_bounce',
            'loss_pct':   round(loss_pct, 2),
            'zone':       zone,
            'bounce':     bounce,
            'new_lowest': new_lowest,
            'recovery_from_low': round(
                recovery_from_low, 2
            ),
            'reason': (
                f'Zona roja CON rebote '
                f'({bounce["score"]:.1f}/10): '
                f'NO cerrar. '
                f'Pérdida: {loss_pct:.2f}%, '
                f'recuperó: +{recovery_from_low:.2f}%'
            ),
        }

    # Sin rebote en zona roja → buscar
    # el mejor momento para cerrar
    # (cuando el precio tenga un pequeño repunte)
    recovery_threshold = float(
        cfg.get('sl_recovery_min_pct', 1.0)
    )
    if recovery_from_low >= recovery_threshold:
        # Aprovechamos el pequeño rebote para cerrar
        return {
            'action':     'close_adaptive',
            'loss_pct':   round(loss_pct, 2),
            'zone':       zone,
            'bounce':     bounce,
            'new_lowest': new_lowest,
            'recovery_from_low': round(
                recovery_from_low, 2
            ),
            'close_reason': (
                f'adaptive_red_zone_recovery'
            ),
            'reason': (
                f'Zona roja: cerrando en rebote '
                f'(+{recovery_from_low:.2f}% desde mín). '
                f'Pérdida final: {loss_pct:.2f}%'
            ),
        }

    # En zona roja sin rebote → esperar
    return {
        'action':     'wait_bounce',
        'loss_pct':   round(loss_pct, 2),
        'zone':       zone,
        'bounce':     bounce,
        'new_lowest': new_lowest,
        'recovery_from_low': round(
            recovery_from_low, 2
        ),
        'days_waiting': days_waiting,
        'reason': (
            f'Zona roja: esperando rebote. '
            f'Pérdida: {loss_pct:.2f}%, '
            f'mín: {lowest_loss_pct:.2f}%. '
            f'Días esperando: {days_waiting}'
        ),
    }


# ═══════════════════════════════════════════
# MÓDULO 5 — EJECUTAR CIERRE ADAPTATIVO
# ═══════════════════════════════════════════

async def execute_adaptive_sl_close(
    ticker:        str,
    position:      dict,
    current_price: float,
    result:        dict,
    supabase,
    ib_provider    = None,
) -> dict:
    """
    Ejecuta el cierre de la posición por SL adaptativo.
    """
    pos_id      = position.get('id')
    entry_price = float(position.get('avg_price') or position.get('entry_price') or 0)

    shares      = int(position.get(
        'shares_remaining',
        position.get('shares', 0)
    ))
    loss_pct    = result.get('loss_pct', 0)
    pnl_usd     = (
        (current_price - entry_price) * shares
    )
    close_reason = result.get(
        'close_reason', 'adaptive_sl'
    )

    log_info('ADAPTIVE_SL',
        f'🔴 SL ADAPTATIVO [{ticker}]: '
        f'vendiendo {shares} shares '
        f'@ ${current_price:.2f} | '
        f'pérdida: {loss_pct:.2f}% '
        f'(${pnl_usd:.2f})'
    )

    # Ejecutar en broker
    try:
        from app.workers.execution_service import get_broker_provider
        provider = await get_broker_provider(position.get('group_name', 'inversiones_pro'))
        if provider:
            await provider.execute_order({
                'ticker': ticker,
                'action': 'SELL',
                'shares': shares,
                'order_type': 'MKT'
            })
    except Exception as e:
        log_error('ADAPTIVE_SL', f'Error Broker Exec: {e}')

    # Cerrar en Supabase
    try:
        await supabase\
            .table('stocks_positions')\
            .update({
                'status':       'closed',
                'updated_at':    datetime.now(
                    timezone.utc
                ).isoformat(),
                'sl_close_reason': result.get(
                    'reason', ''
                )[:200],
                'sl_mode':      'closed',
            })\
            .eq('id', pos_id)\
            .execute()

        # Registrar en stocks_orders
        await supabase\
            .table('stocks_orders')\
            .insert({
                'ticker':       ticker,
                'order_type':   'market',
                'direction':    'sell',
                'shares':       shares,
                'market_price': current_price,
                'rule_code':    'ADAPTIVE_SL',
                'status':       'filled',
                'filled_price': current_price,
                'filled_at':    datetime.now(
                    timezone.utc
                ).isoformat(),
            })\
            .execute()

    except Exception as e:
        log_error('ADAPTIVE_SL',
            f'Error cerrando en DB: {e}'
        )

    # Determinar emoji según la pérdida
    if abs(loss_pct) <= 2:
        emoji = '🟡'   # Pérdida mínima
    elif abs(loss_pct) <= 5:
        emoji = '🟠'   # Pérdida moderada
    else:
        emoji = '🔴'   # Pérdida alta

    try:
        from app.workers.alerts_service import send_telegram_message
        await send_telegram_message(
            f'{emoji} SL ADAPTATIVO [{ticker}]\n'
            f'Razón: {close_reason}\n'
            f'Pérdida: {loss_pct:.2f}%\n'
            f'P&L: ${pnl_usd:.2f}\n'
            f'Precio entrada: ${entry_price:.2f}\n'
            f'Precio salida:  ${current_price:.2f}\n'
            f'Shares: {shares}\n'
            f'Detalle: {result.get("reason","")[:100]}'
        )
    except:
        pass

    return {
        'success':     True,
        'ticker':      ticker,
        'loss_pct':    loss_pct,
        'pnl_usd':     pnl_usd,
        'shares_sold': shares,
        'close_reason': close_reason,
    }

