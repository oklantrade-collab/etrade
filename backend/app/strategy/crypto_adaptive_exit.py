"""
Crypto Adaptive Exit — eTrader v5.0

TP Escalonado Virtual (3 niveles de evaluación).
El cierre es siempre TOTAL cuando se activa.

Integra con:
  - virtual_sl_recovery.py (SLV / Modo Recuperación)
  - safety_manager.py      (Circuit Breaker / SL counter)
  - macro_filter.py        (contexto BTC)
"""

from datetime import datetime, timezone
from app.core.logger import log_info, log_error


# ════════════════════════════════════════════
# TP ESCALONADO VIRTUAL
# ════════════════════════════════════════════

TP_LEVELS_CONFIG = {
    'crypto_futures': {
        # Nivel 1: agotamiento leve — solo alertar
        'level1_score':    5.0,
        'level1_gain_pct': 0.5,
        # Nivel 2: agotamiento moderado — cerrar si ganancia >= 1%
        'level2_score':    7.0,
        'level2_gain_pct': 1.0,
        # Nivel 3: agotamiento fuerte — cerrar siempre si hay ganancia
        'level3_score':    8.5,
        'level3_gain_pct': 0.3,
    },
    'forex_futures': {
        'level1_score':     5.0,
        'level1_gain_pips': 5,
        'level2_score':     7.0,
        'level2_gain_pips': 10,
        'level3_score':     8.5,
        'level3_gain_pips': 3,
    },
}


def evaluate_tp_level(
    exhaustion_score: float,
    pnl_pct:          float,
    pnl_pips:         float = 0.0,
    market_type:      str   = 'crypto_futures',
) -> dict:
    """
    Determina en qué nivel de TP estamos.

    Nivel 0: Sin acción
    Nivel 1: Alerta — monitoreo intensivo
    Nivel 2: TP moderado — cerrar si ganancia OK
    Nivel 3: TP urgente — cerrar siempre

    El cierre SIEMPRE es total cuando se activa.
    """
    cfg = TP_LEVELS_CONFIG.get(
        market_type, TP_LEVELS_CONFIG['crypto_futures']
    )

    if market_type == 'crypto_futures':
        gain = pnl_pct
        l1g  = cfg.get('level1_gain_pct', 0.5)
        l2g  = cfg.get('level2_gain_pct', 1.0)
        l3g  = cfg.get('level3_gain_pct', 0.3)
    else:  # forex
        gain = pnl_pips
        l1g  = cfg.get('level1_gain_pips', 5)
        l2g  = cfg.get('level2_gain_pips', 10)
        l3g  = cfg.get('level3_gain_pips', 3)

    l1s = cfg.get('level1_score', 5.0)
    l2s = cfg.get('level2_score', 7.0)
    l3s = cfg.get('level3_score', 8.5)

    # Nivel 3: Urgente
    if exhaustion_score >= l3s and gain >= l3g:
        return {
            'level':   3,
            'action':  'close_all',
            'urgency': 'high',
            'reason': (
                f'TP Nivel 3 URGENTE: '
                f'score={exhaustion_score:.1f} >= {l3s} '
                f'y ganancia={gain:.2f}'
            ),
        }

    # Nivel 2: Moderado
    if exhaustion_score >= l2s and gain >= l2g:
        return {
            'level':   2,
            'action':  'close_all',
            'urgency': 'medium',
            'reason': (
                f'TP Nivel 2: '
                f'score={exhaustion_score:.1f} >= {l2s} '
                f'y ganancia={gain:.2f}'
            ),
        }

    # Nivel 1: Alerta
    if exhaustion_score >= l1s and gain >= l1g:
        return {
            'level':   1,
            'action':  'alert',
            'urgency': 'low',
            'reason': (
                f'TP Nivel 1 ALERTA: '
                f'score={exhaustion_score:.1f}. '
                f'Monitoreo intensivo...'
            ),
        }

    return {
        'level':   0,
        'action':  'hold',
        'urgency': 'none',
        'reason':  f'Sin trigger (score={exhaustion_score:.1f})',
    }


# ════════════════════════════════════════════
# EVALUACIÓN DE TP ADAPTATIVO PARA CRYPTO
# ════════════════════════════════════════════

def evaluate_crypto_tp(
    symbol:    str,
    positions: list,
    price:     float,
    snap:      dict,
    df_15m=None,
    df_4h=None,
) -> dict:
    """
    Evalúa si se debe cerrar por TP adaptativo.
    Combina exhaustion score del snapshot con
    los niveles de TP escalonados.

    Retorna dict con should_close, pnl, reason.
    """
    if not positions:
        return {'should_close': False, 'reason': 'Sin posiciones'}

    pos = positions[0]
    entry  = float(
        pos.get('avg_entry_price')
        or pos.get('entry_price')
        or pos.get('avg_price') or 0
    )
    side = str(pos.get('side', 'long')).lower()

    if entry <= 0 or price <= 0:
        return {'should_close': False, 'reason': 'Precios inválidos'}

    # Calcular PnL %
    if side in ('long', 'buy'):
        pnl_pct = (price - entry) / entry * 100
    else:
        pnl_pct = (entry - price) / entry * 100

    # Obtener exhaustion score del snapshot
    # (calculado por proactive_exit / band_exit)
    mtf_score = float(snap.get('mtf_score', 0) or 0)
    fib_zone  = int(snap.get('fibonacci_zone', 0) or 0)
    sar_4h    = int(snap.get('sar_trend_4h', 0) or 0)

    # Score de agotamiento (0-10)
    exhaustion = 0.0

    # MTF contrario = agotamiento
    if side in ('long', 'buy') and mtf_score < -0.2:
        exhaustion += abs(mtf_score) * 4
    elif side in ('short', 'sell') and mtf_score > 0.2:
        exhaustion += mtf_score * 4

    # Zona Fibonacci extrema = posible reversal
    if side in ('long', 'buy') and fib_zone >= 3:
        exhaustion += 2.0
    elif side in ('short', 'sell') and fib_zone <= -3:
        exhaustion += 2.0

    # SAR contrario = reversión probable
    if side in ('long', 'buy') and sar_4h < 0:
        exhaustion += 2.0
    elif side in ('short', 'sell') and sar_4h > 0:
        exhaustion += 2.0

    # PineScript contrario
    pine = str(snap.get('pinescript_signal', '') or '')
    if side in ('long', 'buy') and pine == 'Sell':
        exhaustion += 1.5
    elif side in ('short', 'sell') and pine == 'Buy':
        exhaustion += 1.5

    exhaustion = min(10.0, exhaustion)

    tp = evaluate_tp_level(
        exhaustion_score=exhaustion,
        pnl_pct=pnl_pct,
        market_type='crypto_futures',
    )

    if tp['action'] == 'close_all':
        return {
            'should_close':    True,
            'pnl':             round(pnl_pct, 4),
            'tp_level':        tp['level'],
            'exhaustion_score': round(exhaustion, 2),
            'reason':          tp['reason'],
            'close_reason':    f'tp_adaptive_v5_l{tp["level"]}',
        }

    if tp['action'] == 'alert':
        log_info('TP_ADAPTIVE',
                 f'{symbol}: {tp["reason"]} — PnL={pnl_pct:.2f}%')

    return {
        'should_close':     False,
        'pnl':              round(pnl_pct, 4),
        'tp_level':         tp['level'],
        'exhaustion_score': round(exhaustion, 2),
        'reason':           tp['reason'],
    }


# ════════════════════════════════════════════
# EVALUACIÓN DE SL ADAPTATIVO PARA CRYPTO
# ════════════════════════════════════════════

def evaluate_crypto_sl(
    symbol:    str,
    positions: list,
    price:     float,
    snap:      dict,
    df_15m=None,
    df_4h=None,
) -> dict:
    """
    Evalúa si se debe cerrar por SL adaptativo.
    Delega al virtual_sl_recovery si hay SLV activo.
    """
    if not positions:
        return {'should_close': False, 'reason': 'Sin posiciones'}

    pos = positions[0]

    # Si hay modo recuperación activo → delegar a SLVM
    if pos.get('recovery_mode'):
        try:
            from app.strategy.virtual_sl_recovery import (
                evaluate_recovery_mode
            )
            result = evaluate_recovery_mode(
                position=pos,
                current_price=price,
                snap=snap,
                symbol=symbol,
                market_type='crypto_futures',
            )
            result['in_recovery'] = True
            return result
        except Exception as e:
            log_error('ADAPTIVE_SL',
                      f'{symbol}: error en recovery_mode: {e}')

    # Verificar si el SLV fue tocado
    try:
        from app.strategy.virtual_sl_recovery import (
            check_slv_trigger
        )
        if check_slv_trigger(pos, price):
            return {
                'should_close': False,
                'slv_triggered': True,
                'reason': 'SLV tocado — activar recovery_mode',
            }
    except Exception as e:
        log_error('ADAPTIVE_SL',
                  f'{symbol}: error check_slv_trigger: {e}')

    return {'should_close': False, 'reason': 'SL no activado'}


# ════════════════════════════════════════════
# CIERRE TOTAL DE POSICIONES CRYPTO
# ════════════════════════════════════════════

async def close_all_crypto_positions(
    symbol:       str,
    positions:    list,
    price:        float,
    close_reason: str,
    pnl:          float,
    supabase,
    is_tp:        bool = True,
):
    """
    Cierra TODAS las posiciones abiertas de un símbolo.
    Cierre total — sin cierres parciales.
    """
    try:
        from app.core.position_monitor import (
            _execute_paper_close
        )
        for pos in positions:
            await _execute_paper_close(
                pos, price, close_reason, supabase
            )

        emoji = '🟢' if is_tp else '🔴'
        log_info('ADAPTIVE_EXIT',
            f'{emoji} [{symbol}] Cierre total '
            f'({close_reason}): '
            f'PnL={pnl:+.2f}%  '
            f'Precio={price:.6f}'
        )

        try:
            from app.workers.alerts_service import (
                send_telegram_message
            )
            await send_telegram_message(
                f'{emoji} {"TP" if is_tp else "SL"} '
                f'ADAPTATIVO [{symbol}]\n'
                f'Razón: {close_reason}\n'
                f'P&L: {pnl:+.2f}%\n'
                f'Precio: {price:.6f}'
            )
        except Exception:
            pass

    except Exception as e:
        log_error('ADAPTIVE_EXIT',
                  f'{symbol}: error cerrando posiciones: {e}')
