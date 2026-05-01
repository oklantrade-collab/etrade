"""
Forex Adaptive Exit — eTrader v5.0

TP Escalonado Virtual para Forex (pips).
El cierre es siempre TOTAL cuando se activa.
Compatible con: EURUSD, GBPUSD, USDJPY, XAUUSD
"""

from datetime import datetime, timezone
from app.core.logger import log_info, log_error
from app.strategy.crypto_adaptive_exit import (
    TP_LEVELS_CONFIG, evaluate_tp_level
)

PIP_SIZES = {
    'EURUSD': 0.0001,
    'GBPUSD': 0.0001,
    'USDJPY': 0.01,
    'XAUUSD': 0.01,
    'AUDNZD': 0.0001,
    'AUDUSD': 0.0001,
    'NZDUSD': 0.0001,
}


def _pip_size(symbol: str) -> float:
    return PIP_SIZES.get(symbol, 0.0001)


def evaluate_forex_tp(
    symbol:    str,
    positions: list,
    price:     float,
    snap:      dict,
    df_15m=None,
    df_4h=None,
) -> dict:
    """
    Evalúa TP adaptativo para Forex (en pips).
    Usa exhaustion scoring similar a Crypto.
    """
    if not positions:
        return {'should_close': False, 'reason': 'Sin posiciones'}

    pos   = positions[0]
    entry = float(
        pos.get('avg_entry_price')
        or pos.get('entry_price')
        or pos.get('avg_price') or 0
    )
    side  = str(pos.get('side', 'long')).lower()

    if entry <= 0 or price <= 0:
        return {'should_close': False, 'reason': 'Precios inválidos'}

    pip = _pip_size(symbol)
    if side in ('long', 'buy'):
        pnl_pips = (price - entry) / pip
    else:
        pnl_pips = (entry - price) / pip

    pnl_pct = pnl_pips * pip / entry * 100 \
              if entry > 0 else 0.0

    # Score de agotamiento
    mtf_score = float(snap.get('mtf_score', 0) or 0)
    fib_zone  = int(snap.get('fibonacci_zone', 0) or 0)
    sar_4h    = int(snap.get('sar_trend_4h', 0) or 0)
    pine      = str(snap.get('pinescript_signal', '') or '')

    exhaustion = 0.0
    if side in ('long', 'buy') and mtf_score < -0.2:
        exhaustion += abs(mtf_score) * 4
    elif side in ('short', 'sell') and mtf_score > 0.2:
        exhaustion += mtf_score * 4

    if side in ('long', 'buy') and fib_zone >= 3:
        exhaustion += 2.0
    elif side in ('short', 'sell') and fib_zone <= -3:
        exhaustion += 2.0

    if side in ('long', 'buy') and sar_4h < 0:
        exhaustion += 2.0
    elif side in ('short', 'sell') and sar_4h > 0:
        exhaustion += 2.0

    if side in ('long', 'buy') and pine == 'Sell':
        exhaustion += 1.5
    elif side in ('short', 'sell') and pine == 'Buy':
        exhaustion += 1.5

    exhaustion = min(10.0, exhaustion)

    tp = evaluate_tp_level(
        exhaustion_score=exhaustion,
        pnl_pct=pnl_pct,
        pnl_pips=pnl_pips,
        market_type='forex_futures',
    )

    if tp['action'] == 'close_all':
        return {
            'should_close':     True,
            'pnl_pips':         round(pnl_pips, 1),
            'pnl_pct':          round(pnl_pct, 4),
            'tp_level':         tp['level'],
            'exhaustion_score': round(exhaustion, 2),
            'reason':           tp['reason'],
            'close_reason':    f'tp_forex_adaptive_v5_l{tp["level"]}',
        }

    if tp['action'] == 'alert':
        log_info('TP_FOREX',
                 f'{symbol}: {tp["reason"]} — '
                 f'PnL={pnl_pips:.1f} pips')

    return {
        'should_close':     False,
        'pnl_pips':         round(pnl_pips, 1),
        'pnl_pct':          round(pnl_pct, 4),
        'tp_level':         tp['level'],
        'exhaustion_score': round(exhaustion, 2),
        'reason':           tp['reason'],
    }


def evaluate_forex_sl(
    symbol:    str,
    positions: list,
    price:     float,
    snap:      dict,
    df_15m=None,
    df_4h=None,
) -> dict:
    """
    Evalúa SL adaptativo para Forex.
    Delega al virtual_sl_recovery si hay SLV activo.
    """
    if not positions:
        return {'should_close': False, 'reason': 'Sin posiciones'}

    pos = positions[0]

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
                market_type='forex_futures',
            )
            result['in_recovery'] = True
            return result
        except Exception as e:
            log_error('FOREX_SL',
                      f'{symbol}: error recovery_mode: {e}')

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
        log_error('FOREX_SL',
                  f'{symbol}: error check_slv_trigger: {e}')

    return {'should_close': False, 'reason': 'SL no activado'}


async def close_all_forex_positions(
    symbol:       str,
    positions:    list,
    price:        float,
    close_reason: str,
    pnl_pips:     float,
    supabase,
    is_tp:        bool = True,
):
    """
    Cierra TODAS las posiciones Forex de un símbolo.
    """
    try:
        from app.workers.forex_execution_service import (
            ForexExecutionService
        )
        # ForexExecutionService gestiona el cierre real
        for pos in positions:
            pos_id = pos.get('id')
            log_info('FOREX_EXIT',
                f'Cerrando posición {pos_id} '
                f'[{symbol}] vía {close_reason}'
            )
            # Actualizar estado en Supabase
            supabase.table('forex_positions').update({
                'status':       'closed',
                'close_reason': close_reason,
                'closed_at':    datetime.now(timezone.utc).isoformat(),
            }).eq('id', pos_id).execute()

        emoji = '🟢' if is_tp else '🔴'
        log_info('FOREX_EXIT',
            f'{emoji} [{symbol}] Cierre total '
            f'({close_reason}): '
            f'PnL={pnl_pips:+.1f} pips'
        )

        try:
            from app.workers.alerts_service import (
                send_telegram_message
            )
            await send_telegram_message(
                f'{emoji} {"TP" if is_tp else "SL"} '
                f'FOREX ADAPTATIVO [{symbol}]\n'
                f'Razón: {close_reason}\n'
                f'P&L: {pnl_pips:+.1f} pips\n'
                f'Precio: {price:.5f}'
            )
        except Exception:
            pass

    except Exception as e:
        log_error('FOREX_EXIT',
                  f'{symbol}: error cerrando posiciones: {e}')
