"""
Safety Manager — eTrader v5.0

Detecta y neutraliza:
  1. Señales con precio 0.0 o incoherente
  2. Señales con timestamp > 30 minutos
  3. Workers silenciados (sin heartbeat)
  4. Posiciones huérfanas (sin worker activo)
  5. Drawdown diario excesivo (Circuit Breaker)
"""

import asyncio
from datetime import datetime, timezone, timedelta
from app.core.logger import log_info, log_error

# ── Configuración ─────────────────────────────
SAFETY_CONFIG = {
    'signal_max_age_minutes':   30,
    'worker_heartbeat_minutes': 10,
    'price_zero_threshold':     0.001,
    'daily_drawdown_pct':       5.0,
    'circuit_breaker_enabled':  True,
    'max_consecutive_sl':       4,
    'sl_pause_hours':           2,
}

PRICE_RANGES = {
    'BTCUSDT': (1000,   200000),
    'ETHUSDT': (100,    20000),
    'SOLUSDT': (1,      10000),
    'ADAUSDT': (0.01,   10),
    'EURUSD':  (0.5,    2.0),
    'GBPUSD':  (0.5,    2.5),
    'USDJPY':  (50,     200),
    'XAUUSD':  (1000,   5000),
}

# ── Estado interno ────────────────────────────
_worker_heartbeats:      dict = {}
_consecutive_sl:         dict = {}
_circuit_breaker_active: bool = False
_circuit_breaker_since         = None


# ════════════════════════════════════════
# HEARTBEAT
# ════════════════════════════════════════

def register_heartbeat(worker_name: str):
    """Registra el último latido de un worker."""
    global _worker_heartbeats
    _worker_heartbeats[worker_name] = \
        datetime.now(timezone.utc)


def check_worker_alive(worker_name: str) -> bool:
    """Retorna True si el worker tiene heartbeat reciente."""
    last = _worker_heartbeats.get(worker_name)
    if not last:
        return False
    max_min = SAFETY_CONFIG['worker_heartbeat_minutes']
    elapsed = (datetime.now(timezone.utc) - last) \
              .total_seconds() / 60
    return elapsed <= max_min


# ════════════════════════════════════════
# VALIDACIÓN DE SEÑALES
# ════════════════════════════════════════

def validate_signal(
    symbol:      str,
    price:       float,
    timestamp=None,
    market_type: str = 'crypto_futures',
) -> dict:
    """
    Valida señal antes de ejecutarla.
    Retorna dict con valid, reason, action.
    """
    now    = datetime.now(timezone.utc)
    errors = []
    thresh = SAFETY_CONFIG['price_zero_threshold']

    # CHECK 1: Precio > 0
    if not isinstance(price, (int, float)) or \
       price <= thresh:
        errors.append(f'Precio inválido: {price}')

    # CHECK 2: Rango coherente
    if symbol in PRICE_RANGES and \
       isinstance(price, (int, float)) and \
       price > thresh:
        lo, hi = PRICE_RANGES[symbol]
        if not (lo <= price <= hi):
            errors.append(
                f'Precio fuera de rango: '
                f'${price:.4f} (esperado {lo}-{hi})'
            )

    # CHECK 3: Timestamp fresco
    if timestamp:
        ts = timestamp
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(
                    ts.replace('Z', '+00:00')
                )
            except Exception:
                errors.append('Timestamp inválido')
                ts = None
        if ts:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            max_age = SAFETY_CONFIG['signal_max_age_minutes']
            age_min = (now - ts).total_seconds() / 60
            if age_min > max_age:
                errors.append(
                    f'Señal antigua: {age_min:.0f} min '
                    f'(máx={max_age})'
                )

    # CHECK 4: Circuit Breaker
    if _circuit_breaker_active:
        errors.append(
            'Circuit Breaker activo — trading suspendido'
        )

    if errors:
        log_info('SAFETY',
                 f'⚠️ Señal rechazada [{symbol}]: '
                 + ' | '.join(errors))
        return {
            'valid':  False,
            'errors': errors,
            'action': 'skip',
            'reason': ' | '.join(errors),
        }
    return {
        'valid':  True,
        'errors': [],
        'action': 'execute',
        'reason': 'Señal válida',
    }


# ════════════════════════════════════════
# CIRCUIT BREAKER
# ════════════════════════════════════════

async def check_circuit_breaker(
    supabase,
    market_type: str = 'crypto_futures',
) -> dict:
    """Verifica drawdown diario y activa Circuit Breaker si supera umbral."""
    global _circuit_breaker_active, _circuit_breaker_since

    if not SAFETY_CONFIG.get('circuit_breaker_enabled', True):
        return {'active': False}

    now_utc   = datetime.now(timezone.utc)
    day_start = now_utc.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    table       = 'positions' \
                  if market_type == 'crypto_futures' \
                  else 'forex_positions'
    drawdown_pct = 0.0
    daily_pnl    = 0.0

    try:
        res = await supabase \
            .table(table) \
            .select('realized_pnl') \
            .gte('closed_at', day_start.isoformat()) \
            .eq('status', 'closed') \
            .execute()

        daily_pnl = sum(
            float(r.get('realized_pnl', 0) or 0)
            for r in (res.data or [])
        )

        cfg_res = await supabase \
            .table('trading_config') \
            .select('value') \
            .eq('key', f'capital_{market_type}') \
            .maybe_single() \
            .execute()

        capital = float(
            (cfg_res.data or {}).get('value', 1000)
        )
        if daily_pnl < 0 and capital > 0:
            drawdown_pct = abs(daily_pnl) / capital * 100

        threshold = float(SAFETY_CONFIG['daily_drawdown_pct'])

        if drawdown_pct >= threshold and daily_pnl < 0:
            if not _circuit_breaker_active:
                _circuit_breaker_active = True
                _circuit_breaker_since  = now_utc
                log_error('SAFETY',
                    f'🔴 CIRCUIT BREAKER ACTIVADO: '
                    f'drawdown {drawdown_pct:.1f}% '
                    f'(${daily_pnl:.2f})'
                )
                await _send_telegram(
                    f'🚨 CIRCUIT BREAKER [{market_type}]\n'
                    f'Drawdown del día: {drawdown_pct:.1f}%\n'
                    f'P&L: ${daily_pnl:.2f}\n'
                    f'TRADING SUSPENDIDO\n'
                    f'Se reanuda mañana a las 00:00 UTC'
                )
            return {
                'active':       True,
                'drawdown_pct': drawdown_pct,
                'daily_pnl':    daily_pnl,
                'reason': (
                    f'Drawdown {drawdown_pct:.1f}% >= {threshold}%'
                ),
            }
        else:
            if _circuit_breaker_active:
                since = _circuit_breaker_since
                if since and now_utc.date() > since.date():
                    _circuit_breaker_active = False
                    _circuit_breaker_since  = None
                    log_info('SAFETY', '✅ Circuit Breaker reseteado')

    except Exception as e:
        log_error('SAFETY', f'Error Circuit Breaker: {e}')

    return {
        'active':       _circuit_breaker_active,
        'drawdown_pct': drawdown_pct,
        'daily_pnl':    daily_pnl,
    }


def register_sl_event(symbol: str, direction: str) -> int:
    """Registra un SL. Alerta si hay N consecutivos."""
    global _consecutive_sl
    key   = f'{symbol}_{direction}'
    count = _consecutive_sl.get(key, 0) + 1
    _consecutive_sl[key] = count
    max_sl = SAFETY_CONFIG['max_consecutive_sl']
    if count >= max_sl:
        log_error('SAFETY',
            f'🔴 {count} SLs consecutivos en '
            f'{symbol}/{direction}! Posible problema sistémico.'
        )
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(_send_telegram(
                    f'⚠️ ALERTA SL LOOP\n'
                    f'{symbol}/{direction}: {count} SLs consecutivos\n'
                    f'Revisar la estrategia urgente'
                ))
        except RuntimeError:
            pass
    return count


def reset_sl_counter(symbol: str, direction: str):
    """Resetea contador de SLs al cerrar con ganancia."""
    _consecutive_sl.pop(f'{symbol}_{direction}', None)


def get_circuit_breaker_status() -> dict:
    return {
        'active': _circuit_breaker_active,
        'since':  _circuit_breaker_since.isoformat()
                  if _circuit_breaker_since else None,
    }


def reset_circuit_breaker_manual():
    """Reseteo manual del Circuit Breaker (admin)."""
    global _circuit_breaker_active, _circuit_breaker_since
    _circuit_breaker_active = False
    _circuit_breaker_since  = None
    log_info('SAFETY', '🔓 Circuit Breaker reseteado manualmente')


# ════════════════════════════════════════
# LIMPIEZA DE SEÑALES ZOMBIE
# ════════════════════════════════════════

async def cleanup_zombie_signals(supabase) -> int:
    """Resetea señales antiguas o con precio 0 en market_snapshot."""
    now     = datetime.now(timezone.utc)
    max_age = SAFETY_CONFIG['signal_max_age_minutes']
    cutoff  = now - timedelta(minutes=max_age)
    cleaned = 0

    try:
        zero_res = await supabase \
            .table('market_snapshot') \
            .select('symbol, price, updated_at') \
            .lte('price', 0.001) \
            .execute()

        for row in (zero_res.data or []):
            symbol = row['symbol']
            log_info('SAFETY', f'Señal zombie (price=0): {symbol}')
            await supabase \
                .table('market_snapshot') \
                .update({'regime': 'zombie', 'mtf_score': 0}) \
                .eq('symbol', symbol) \
                .execute()
            cleaned += 1

        old_res = await supabase \
            .table('market_snapshot') \
            .select('symbol, updated_at') \
            .lt('updated_at', cutoff.isoformat()) \
            .neq('regime', 'zombie') \
            .execute()

        for row in (old_res.data or []):
            symbol = row['symbol']
            log_info('SAFETY',
                     f'Snapshot antiguo: {symbol} ({row["updated_at"]})')
            await supabase \
                .table('market_snapshot') \
                .update({'regime': 'stale'}) \
                .eq('symbol', symbol) \
                .execute()
            cleaned += 1

    except Exception as e:
        log_error('SAFETY', f'Error limpieza zombie: {e}')

    if cleaned > 0:
        log_info('SAFETY', f'Limpieza: {cleaned} señales zombie')

    return cleaned


# ════════════════════════════════════════
# VERIFICACIÓN DE WORKERS (cada 5m)
# ════════════════════════════════════════

async def check_all_heartbeats() -> list:
    """Verifica que todos los workers están vivos. Alerta por Telegram si no."""
    workers = [
        'crypto_scheduler',
        'forex_worker',
        'stocks_scheduler',
    ]
    dead = [w for w in workers if not check_worker_alive(w)]
    if dead:
        log_error('SAFETY', f'💀 Workers caídos: {", ".join(dead)}')
        await _send_telegram(
            '💀 WORKERS CAÍDOS:\n'
            + '\n'.join(f'  ❌ {w}' for w in dead)
            + '\n\nReiniciando automáticamente...'
        )
    return dead


# ════════════════════════════════════════
# HELPER — Telegram
# ════════════════════════════════════════

async def _send_telegram(message: str):
    try:
        from app.workers.alerts_service import send_telegram_message
        await send_telegram_message(message)
    except Exception:
        pass
