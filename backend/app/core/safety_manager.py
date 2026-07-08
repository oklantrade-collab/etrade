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

def safe_float(val, default=0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def safe_int(val, default=0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def get_rule_expected_direction(rule_code: str) -> str:
    if not rule_code:
        return None
    if isinstance(rule_code, dict):
        rc = str(rule_code.get('code', rule_code.get('name', ''))).strip().lower()
    else:
        rc = str(rule_code).strip().lower()
    if rc.startswith('dd11'):
        return 'long'
    if rc.startswith('dd12'):
        return 'short'
    if rc.startswith('aa'):
        if 'short' in rc:
            return 'short'
        return 'long'
    if rc.startswith('bb'):
        return 'short'
    return None

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
_worker_heartbeats:      dict = {
    'position_monitor': datetime.now(timezone.utc),
    'crypto_scheduler': datetime.now(timezone.utc),
}
_consecutive_sl:         dict = {}
_circuit_breaker_active: bool = False
_circuit_breaker_since         = None
_current_worker:         str  = None
_safety_block_forex:     bool = False
_safety_block_crypto:    bool = False
_last_safety_check_time         = None

def is_forex_safety_blocked() -> bool:
    global _safety_block_forex
    return _safety_block_forex

def is_crypto_safety_blocked() -> bool:
    global _safety_block_crypto
    return _safety_block_crypto

def set_forex_safety_block(blocked: bool):
    global _safety_block_forex
    _safety_block_forex = blocked

def set_crypto_safety_block(blocked: bool):
    global _safety_block_crypto
    _safety_block_crypto = blocked

def check_db_safety_block(market_type: str) -> bool:
    """Consulta en base de datos si existe bloqueo de seguridad en regime_params."""
    try:
        from app.core.supabase_client import get_supabase
        sb = get_supabase()
        res = sb.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
        if res and res.data:
            params = res.data.get('regime_params') or {}
            if market_type == 'forex_futures':
                return bool(params.get('safety_blocked_forex', False))
            elif market_type == 'crypto_futures':
                return bool(params.get('safety_blocked_crypto', False))
    except Exception:
        pass
    return False

def update_db_safety_block(market_type: str, blocked: bool):
    """Actualiza en base de datos el estado del bloqueo de seguridad en regime_params."""
    try:
        from app.core.supabase_client import get_supabase
        sb = get_supabase()
        res = sb.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
        if res and res.data:
            params = res.data.get('regime_params') or {}
            key = 'safety_blocked_forex' if market_type == 'forex_futures' else 'safety_blocked_crypto'
            params[key] = blocked
            params['safety_checked_at'] = datetime.now(timezone.utc).isoformat()
            sb.table('trading_config').update({'regime_params': params}).eq('id', 1).execute()
    except Exception as e:
        log_error('SAFETY', f"Error actualizando bloqueo en DB: {e}")

def set_current_worker(name: str):
    global _current_worker
    _current_worker = name
    register_heartbeat(name)


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
    direction:   str = None,
    rule_code:   str = None,
    snap:        dict = None,
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
            if isinstance(ts, (int, float)):
                # Convertir timestamp (s o ms) a datetime
                if ts > 1e12: ts /= 1000 # ms to s
                ts = datetime.fromtimestamp(ts, tz=timezone.utc)
            
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

    # CHECK 5: Bloqueos de Seguridad por Subprocesos
    if market_type == 'forex_futures' and (_safety_block_forex or check_db_safety_block('forex_futures')):
        errors.append('Bloqueo de Seguridad FOREX activo por fallo en subprocesos críticos')
    elif market_type == 'crypto_futures' and (_safety_block_crypto or check_db_safety_block('crypto_futures')):
        errors.append('Bloqueo de Seguridad CRYPTO activo por fallo en subprocesos críticos')

    # CHECK 6: Coherencia de Regla vs Dirección
    if direction and rule_code:
        expected = get_rule_expected_direction(rule_code)
        if expected and expected != str(direction).strip().lower():
            rc_str = rule_code.get('code', str(rule_code)) if isinstance(rule_code, dict) else str(rule_code)
            errors.append(
                f"Dirección incoherente para la regla: "
                f"regla {rc_str} ({expected}) != dirección {direction}"
            )

    # CHECK 7: Sanidad de Indicadores Técnicos en el Snapshot
    if snap:
        critical_keys = ['price']
        if market_type == 'forex_futures':
            critical_keys.extend(['ema_3', 'ema_9', 'ema_20', 'atr', 'adx'])
        elif market_type == 'crypto_futures':
            critical_keys.extend(['ema_3', 'ema_9'])
            
        had_check7_error = False
        check7_errors = []
        for key in critical_keys:
            val = snap.get(key)
            if val is None:
                err_msg = f"Indicador crítico ausente/nulo: '{key}'"
                errors.append(err_msg)
                check7_errors.append(err_msg)
                had_check7_error = True
            elif isinstance(val, (int, float)) and val <= 0 and key != 'sar_trend_4h' and key != 'sar_trend_15m':
                err_msg = f"Indicador crítico con valor inválido: '{key}' = {val}"
                errors.append(err_msg)
                check7_errors.append(err_msg)
                had_check7_error = True

        if had_check7_error:
            # Activar bloqueo de seguridad preventivo a nivel de sistema (in-memory y base de datos)
            if market_type == 'forex_futures':
                set_forex_safety_block(True)
                update_db_safety_block('forex_futures', True)
                market_name = "FOREX"
            else:
                set_crypto_safety_block(True)
                update_db_safety_block('crypto_futures', True)
                market_name = "CRYPTO"
            
            alert_msg = (
                f"🚨 **BLOQUEO PREVENTIVO DE SEGURIDAD ACTIVADO ({market_name})**\n\n"
                f"El motor de seguridad detectó datos corruptos, nulos o desfasados en indicadores técnicos antes de operar en **{symbol}**.\n\n"
                f"**Detalles del fallo:**\n"
                + "\n".join(f"• {e}" for e in check7_errors) + "\n\n"
                f"🛑 **Acción Preventiva:** Se suspende inmediatamente todo el ingreso de nuevas compras u operaciones en {market_name} "
                f"de manera preventiva hasta que se corrija el problema técnico en los servidores."
            )
            send_telegram_sync(alert_msg)

    # CHECK 8: Control de sobrecompra / sobreventa Bollinger para Forex (e.g. Aa52/Bb52)
    if not errors and snap and market_type == 'forex_futures' and direction and rule_code:
        rc = str(rule_code).strip().lower()
        if 'aa52' in rc or 'bb52' in rc:
            bb_upper = safe_float(snap.get('upper_2'))
            bb_lower = safe_float(snap.get('lower_2'))
            
            if direction.lower() == 'long' and bb_upper > 0:
                if price >= bb_upper:
                    errors.append(
                        f"Filtro sobrecompra Bollinger (Aa52) activo: precio ${price:.5f} >= bb_upper (upper_2) ${bb_upper:.5f}"
                    )
            elif direction.lower() == 'short' and bb_lower > 0:
                if price <= bb_lower:
                    errors.append(
                        f"Filtro sobreventa Bollinger (Bb52) activo: precio ${price:.5f} <= bb_lower (lower_2) ${bb_lower:.5f}"
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
        res = supabase \
            .table(table) \
            .select('realized_pnl') \
            .gte('closed_at', day_start.isoformat()) \
            .eq('status', 'closed') \
            .execute()

        daily_pnl = 0.0
        if res and hasattr(res, 'data') and res.data:
            daily_pnl = sum(
                float(r.get('realized_pnl', 0) or 0)
                for r in res.data
            )

        cfg_res = supabase \
            .table('trading_config') \
            .select('*') \
            .eq('id', 1) \
            .maybe_single() \
            .execute()

        capital = 1000.0
        if cfg_res and hasattr(cfg_res, 'data') and cfg_res.data:
            cap_val = cfg_res.data.get(f'capital_{market_type}')
            if not cap_val:
                cap_val = cfg_res.data.get('capital_operativo', cfg_res.data.get('capital_total', 1000))
            capital = float(cap_val or 1000)
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
        zero_res = supabase \
            .table('market_snapshot') \
            .select('symbol, price, updated_at') \
            .lte('price', 0.001) \
            .execute()

        for row in (zero_res.data or []):
            symbol = row['symbol']
            log_info('SAFETY', f'Señal zombie (price=0): {symbol}')
            supabase \
                .table('market_snapshot') \
                .update({'regime': 'zombie', 'mtf_score': 0}) \
                .eq('symbol', symbol) \
                .execute()
            cleaned += 1

        old_res = supabase \
            .table('market_snapshot') \
            .select('symbol, updated_at') \
            .lt('updated_at', cutoff.isoformat()) \
            .neq('regime', 'zombie') \
            .execute()

        for row in (old_res.data or []):
            symbol = row['symbol']
            log_info('SAFETY',
                     f'Snapshot antiguo: {symbol} ({row["updated_at"]})')
            supabase \
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


async def check_subprocesses_safety(supabase) -> dict:
    """
    Ejecuta el control de seguridad exhaustivo cada 15 minutos.
    Valida subprocesos clave en controles de Stop Loss, SL Virtual (SLVM),
    Stop Loss Adaptativo e indicadores para los mercados de Crypto y Forex.
    Activa bloqueos y alerta a Telegram en caso de fallos.
    """
    global _safety_block_forex, _safety_block_crypto, _last_safety_check_time
    now = datetime.now(timezone.utc)
    _last_safety_check_time = now
    
    forex_checks = {}
    crypto_checks = {}
    pos_monitor_mem_alive = check_worker_alive('position_monitor')
    
    # ────────────────────────────────────────────────────────────────
    # FOREX SAFETY CHECKLIST
    # ────────────────────────────────────────────────────────────────
    try:
        # Check 2.1: Heartbeat de forex_worker (latido de Twist reactor)
        forex_worker_mem_alive = check_worker_alive('forex_worker')
        
        # Check 2.2: Frescura de datos en snapshot (Feed Price)
        forex_symbols = ['EURUSD', 'GBPUSD', 'XAUUSD', 'USDJPY']
        snap_res = supabase.table('market_snapshot').select('symbol, price, updated_at, atr, basis').in_('symbol', forex_symbols).execute()
        
        snaps = {r['symbol']: r for r in snap_res.data} if snap_res and snap_res.data else {}
        
        stale_forex = False
        indicators_crashed_forex = False
        for sym in forex_symbols:
            s_data = snaps.get(sym)
            if not s_data:
                stale_forex = True
                continue
            
            ts_str = s_data.get('updated_at')
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                if (now - ts).total_seconds() > 900: # 15 minutos
                    stale_forex = True
            else:
                stale_forex = True
                
            # Check 2.5: Indicadores Adaptativos (basis)
            basis_val = float(s_data.get('basis') or 0)
            if basis_val <= 0:
                indicators_crashed_forex = True
        
        # Check 2.3: Integridad de Stop Loss en posiciones abiertas (exceptuando si EREP está activo o son de ApexEma)
        pos_res = supabase.table('forex_positions').select('id, symbol, sl_price, tp_price, erep_active, erep_phase, rule_code').eq('status', 'open').execute()
        open_pos_list = pos_res.data or []
        
        pos_missing_sl_forex = False
        for pos in open_pos_list:
            if bool(pos.get('erep_active')) or safe_int(pos.get('erep_phase')) > 0:
                continue
            if pos.get('rule_code') in ('AaApexEma', 'BbApexEma'):
                continue
            sl = float(pos.get('sl_price') or 0)
            tp = float(pos.get('tp_price') or 0)
            if sl <= 0 or tp <= 0:
                pos_missing_sl_forex = True
                
        # Consolidar Checks de Forex
        forex_checks['worker_heartbeat'] = forex_worker_mem_alive or not stale_forex
        forex_checks['feed_freshness'] = not stale_forex
        forex_checks['stop_loss_integrity'] = not pos_missing_sl_forex
        forex_checks['adaptive_indicators'] = not indicators_crashed_forex
        forex_checks['position_monitor_heartbeat'] = pos_monitor_mem_alive
        
        # Check 2.4: Integridad del SLVM (Modo Recuperación)
        forex_checks['slvm_integrity'] = True
        
    except Exception as e:
        log_error('SAFETY', f"Error ejecutando checklist de FOREX: {e}")
        forex_checks['system_error'] = False
        
    # Calcular resultado Forex
    forex_failed = any(v is False for v in forex_checks.values())
    
    # ── EMERGENCY GUARDS HOOK (FOREX) ──
    from app.strategy.emergency_guards import trigger_emergency_protection, restore_emergency_protection
    was_forex_blocked = check_db_safety_block('forex_futures')
    if forex_failed and not was_forex_blocked:
        # Acaba de entrar en emergencia
        import asyncio
        asyncio.create_task(trigger_emergency_protection('forex_futures'))
    elif not forex_failed and was_forex_blocked:
        # Acaba de salir de emergencia
        import asyncio
        asyncio.create_task(restore_emergency_protection('forex_futures'))

    set_forex_safety_block(forex_failed)
    update_db_safety_block('forex_futures', forex_failed)
    
    # ────────────────────────────────────────────────────────────────
    # CRYPTO SAFETY CHECKLIST
    # ────────────────────────────────────────────────────────────────
    try:
        # Check 1.1: Heartbeat de crypto_scheduler
        crypto_worker_mem_alive = check_worker_alive('crypto_scheduler')
        
        # Check 1.2: Frescura de datos en snapshot (Feed Price)
        crypto_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        snap_res_crypto = supabase.table('market_snapshot').select('symbol, price, updated_at, atr, basis').in_('symbol', crypto_symbols).execute()
        
        snaps_crypto = {r['symbol']: r for r in snap_res_crypto.data} if snap_res_crypto and snap_res_crypto.data else {}
        
        stale_crypto = False
        indicators_crashed_crypto = False
        stale_count_crypto = 0
        for sym in crypto_symbols:
            s_data = snaps_crypto.get(sym)
            if not s_data:
                stale_count_crypto += 1
                continue
            
            ts_str = s_data.get('updated_at')
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                if (now - ts).total_seconds() > 1800: # V6: 30 minutos (antes: 15 min) - tolerancia para ciclos crypto
                    stale_count_crypto += 1
            else:
                stale_count_crypto += 1
                
            # Check 1.4: Indicadores Adaptativos (basis)
            basis_val = float(s_data.get('basis') or 0)
            if basis_val <= 0:
                indicators_crashed_crypto = True
        
        # V6: Solo marcar stale si la MAYORÍA de símbolos están desactualizados (2+ de 3)
        stale_crypto = stale_count_crypto >= 2
                
        # Check 1.3: Integridad de Stop Loss en posiciones abiertas de Crypto (exceptuando si EREP está activo o son de ApexEma)
        pos_res_crypto = supabase.table('positions').select('id, symbol, sl_price, tp_full_price, erep_active, erep_phase, rule_code').eq('status', 'open').execute()
        open_pos_list_crypto = pos_res_crypto.data or []
        
        pos_missing_sl_crypto = False
        for pos in open_pos_list_crypto:
            if bool(pos.get('erep_active')) or safe_int(pos.get('erep_phase')) > 0:
                continue
            if pos.get('rule_code') in ('AaApexEma', 'BbApexEma'):
                continue
            sl = float(pos.get('sl_price') or 0)
            tp = float(pos.get('tp_full_price') or 0)
            if sl <= 0 or tp <= 0:
                pos_missing_sl_crypto = True
                
        # Consolidar Checks de Crypto
        crypto_checks['worker_heartbeat'] = crypto_worker_mem_alive or not stale_crypto
        crypto_checks['feed_freshness'] = not stale_crypto
        crypto_checks['stop_loss_integrity'] = not pos_missing_sl_crypto
        crypto_checks['adaptive_indicators'] = not indicators_crashed_crypto
        crypto_checks['position_monitor_heartbeat'] = pos_monitor_mem_alive
        
    except Exception as e:
        log_error('SAFETY', f"Error ejecutando checklist de CRYPTO: {e}")
        crypto_checks['system_error'] = False
        
    # Calcular resultado Crypto
    crypto_failed = any(v is False for v in crypto_checks.values())
    
    # ── EMERGENCY GUARDS HOOK (CRYPTO) ──
    from app.strategy.emergency_guards import trigger_emergency_protection, restore_emergency_protection
    was_crypto_blocked = check_db_safety_block('crypto_futures')
    if crypto_failed and not was_crypto_blocked:
        # Acaba de entrar en emergencia
        import asyncio
        asyncio.create_task(trigger_emergency_protection('crypto_futures'))
    elif not crypto_failed and was_crypto_blocked:
        # Acaba de salir de emergencia
        import asyncio
        asyncio.create_task(restore_emergency_protection('crypto_futures'))

    set_crypto_safety_block(crypto_failed)
    update_db_safety_block('crypto_futures', crypto_failed)
    
    # ────────────────────────────────────────────────────────────────
    # REPORTING & TELEGRAM ALERTS
    # ────────────────────────────────────────────────────────────────
    # Alerta Forex
    if forex_failed:
        report_msg = (
            "🚨 **FALLO DE SUBPROCESOS CRÍTICOS - MERCADO FOREX**\n"
            "El control automático de seguridad de 15 min detectó fallos:\n"
        )
        for name, ok in forex_checks.items():
            icon = "✅ OK" if ok else "❌ FALLÓ"
            report_msg += f"- [{name}]: {icon}\n"
        report_msg += (
            "\n⚠️ **ACCIÓN DE EMERGENCIA**: Se ha activado el bloqueo de seguridad para FOREX. "
            "El sistema tiene prohibido comprar/vender cualquier activo de Forex hasta solucionar los problemas."
        )
        await _send_telegram(report_msg)
        log_error('SAFETY', f"Bloqueo de Seguridad FOREX activado. Diagnóstico: {forex_checks}")
    else:
        # Si estaba bloqueado anteriormente, alertamos que se solucionó
        if check_db_safety_block('forex_futures'):
            await _send_telegram("✅ **SISTEMA RESTAURADO - MERCADO FOREX**\nTodos los subprocesos de Forex operan con normalidad. Bloqueo de seguridad levantado.")
        log_info('SAFETY', "✅ Control de Seguridad de 15m para FOREX completado exitosamente (Sin fallos).")
        
    # Alerta Crypto
    if crypto_failed:
        from app.execution.data_provider import BinanceCryptoProvider
        if BinanceCryptoProvider.is_banned() and crypto_checks.get('stop_loss_integrity') and crypto_checks.get('adaptive_indicators'):
            log_info('SAFETY', f"Bloqueo de Seguridad CRYPTO mantenido por BAN de Binance. Diagnóstico: {crypto_checks}. Omitiendo alerta de Telegram.")
        else:
            report_msg = (
                "🚨 **FALLO DE SUBPROCESOS CRÍTICOS - MERCADO CRYPTO**\n"
                "El control automático de seguridad de 15 min detectó fallos:\n"
            )
            for name, ok in crypto_checks.items():
                icon = "✅ OK" if ok else "❌ FALLÓ"
                report_msg += f"- [{name}]: {icon}\n"
            report_msg += (
                "\n⚠️ **ACCIÓN DE EMERGENCIA**: Se ha activado el bloqueo de seguridad para CRYPTO. "
                "El sistema tiene prohibido comprar/vender cualquier activo de Crypto hasta solucionar los problemas."
            )
            await _send_telegram(report_msg)
            log_error('SAFETY', f"Bloqueo de Seguridad CRYPTO activado. Diagnóstico: {crypto_checks}")
    else:
        # Si estaba bloqueado anteriormente, alertamos que se solucionó
        if check_db_safety_block('crypto_futures'):
            await _send_telegram("✅ **SISTEMA RESTAURADO - MERCADO CRYPTO**\nTodos los subprocesos de Crypto operan con normalidad. Bloqueo de seguridad levantado.")
        log_info('SAFETY', "✅ Control de Seguridad de 15m para CRYPTO completado exitosamente (Sin fallos).")
        
    return {
        'forex': {'failed': forex_failed, 'checks': forex_checks},
        'crypto': {'failed': crypto_failed, 'checks': crypto_checks}
    }


# ════════════════════════════════════════
# VERIFICACIÓN DE WORKERS (cada 5m)
# ════════════════════════════════════════

async def check_all_heartbeats() -> list:
    """Verifica que todos los workers están vivos. Alerta por Telegram si no."""
    from app.core.supabase_client import get_supabase
    sb = get_supabase()
    
    workers_map = {
        'crypto_scheduler': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
        'forex_worker':     ['EURUSD', 'GBPUSD', 'XAUUSD'],
        'position_monitor': [],
        'stocks_scheduler': []
    }
    
    dead = []
    now = datetime.now(timezone.utc)
    max_age = SAFETY_CONFIG['worker_heartbeat_minutes']
    
    for w_name, symbols in workers_map.items():
        # 1. Si es el worker actual o un worker de memoria crítica, chequear memoria
        if w_name == _current_worker or w_name in ['position_monitor', 'crypto_scheduler']:
            if not check_worker_alive(w_name):
                dead.append(w_name)
            continue
            
        # 2. Si no, chequear DB (market_snapshot) como proxy
        try:
            # Especial para stocks: si el mercado está cerrado, no reportar caída.
            # Además, añadimos un periodo de gracia de 15 minutos desde la apertura (09:30 ET)
            # para dar tiempo a que el scheduler corra su primer ciclo y actualice los snapshots.
            if w_name == 'stocks_scheduler':
                from app.core.market_hours import is_market_open, get_nyc_now
                from datetime import time
                is_open, _ = is_market_open()
                if not is_open:
                    continue
                
                nyc_now = get_nyc_now().replace(tzinfo=None)
                market_open_dt = datetime.combine(nyc_now.date(), time(9, 30))
                minutes_since_open = (nyc_now - market_open_dt).total_seconds() / 60.0
                if 0 <= minutes_since_open < 15:
                    continue

            if w_name == 'stocks_scheduler':
                # Dinámico: en lugar de buscar tickers estáticos, buscamos el registro más reciente
                # de CUALQUIER acción (excluyendo cripto y forex representativos) en market_snapshot.
                exclude_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'EURUSD', 'GBPUSD', 'XAUUSD']
                res = sb.table('market_snapshot')\
                        .select('updated_at')\
                        .not_.in_('symbol', exclude_symbols)\
                        .order('updated_at', desc=True)\
                        .limit(1)\
                        .execute()
            else:
                res = sb.table('market_snapshot').select('updated_at').in_('symbol', symbols).execute()
                
            if not res.data:
                dead.append(w_name)
                continue
            
            # Ver si el más reciente es joven
            latest_update = None
            for row in res.data:
                ts_str = row.get('updated_at')
                if ts_str:
                    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    if latest_update is None or ts > latest_update:
                        latest_update = ts
            
            if not latest_update:
                dead.append(w_name)
            else:
                elapsed = (now - latest_update).total_seconds() / 60
                if elapsed > max_age + 5: # Damos 5 min extra de margen por latencia DB
                    dead.append(w_name)
        except Exception as e:
            log_error('SAFETY', f'Error verificando heartbeat DB para {w_name}: {e}')
            # Si falla la DB, no marcamos como muerto para evitar spam si es solo un problema de red
            pass

    if dead:
        log_error('SAFETY', f'💀 Workers caídos (DB/Mem): {", ".join(dead)}')
        # Solo enviar alerta si el fallo persiste o si somos el worker principal (crypto_scheduler)
        if _current_worker == 'crypto_scheduler':
            await _send_telegram(
                '💀 ALERTA DE SISTEMA SAFETY\n'
                'Se detectaron workers sin actividad reciente:\n'
                + '\n'.join(f'  ❌ {w}' for w in dead)
                + '\n\nRevisar estado de procesos en el servidor.'
            )
    return dead


async def _send_telegram(message: str):
    try:
        from app.workers.alerts_service import send_telegram_message
        await send_telegram_message(message)
    except Exception:
        pass

def send_telegram_sync(message: str):
    """Envía un mensaje de Telegram desde un contexto síncrono de forma segura."""
    try:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            from app.workers.alerts_service import send_telegram_message
            loop.create_task(send_telegram_message(message))
        else:
            import threading
            from app.workers.alerts_service import send_telegram_message
            def run_sync():
                try:
                    asyncio.run(send_telegram_message(message))
                except Exception:
                    pass
            threading.Thread(target=run_sync, daemon=True).start()
    except Exception as e:
        log_error('SAFETY', f"Error enviando Telegram síncrono: {e}")
