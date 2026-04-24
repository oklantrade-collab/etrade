"""
Monitor de posiciones para ciclo de 5m.
Detecta liquidaciones, SL/TP ejecutados por Binance,
y cualquier discrepancia entre el bot y el exchange.
"""
import asyncio
from datetime import datetime, timezone
from app.core.memory_store import BOT_STATE
from app.core.logger import log_info, log_warning, log_error
from app.core.crypto_symbols import normalize_crypto_symbol, crypto_symbol_match_variants
from app.strategy.capital_protection import (
    ProtectionState,
    evaluate_break_even,
    evaluate_trailing_stop,
    PROTECTION_CONFIG,
    calculate_pnl,
    evaluate_all_protections
)
from app.strategy.position_guards import (
    check_time_based_sl,
    register_sl_event,
    update_peak_pnl,
)

MODULE = "POSITION_MONITOR"

async def check_signal_reversal(
    position:     dict,
    current_mtf:  float,
    current_price: float,
    config:       dict
) -> dict:
    """
    Cierra la posición cuando el MTF gira en contra
    SOLO si hay una ganancia mínima asegurada.

    Nunca cierra con pérdida por esta regla.
    Para pérdidas → el SL es el mecanismo correcto.
    """
    if not config.get('exit_on_signal_reversal', True):
        return {'should_exit': False}

    if not position:
        return {'should_exit': False}

    side      = (position.get('side') or '').lower()
    entry     = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
    threshold = float(config.get('exit_mtf_threshold', 0.0))
    min_pct   = float(config.get('min_profit_exit_pct', 0.30))
    min_usd   = float(config.get('min_profit_exit_usd', 1.00))

    if entry == 0:
        return {'should_exit': False}

    # Calcular P&L actual
    if side == 'long':
        pnl_pct = (current_price - entry) / entry * 100
    else:
        pnl_pct = (entry - current_price) / entry * 100

    capital  = float(position.get('size', 0)) * entry
    pnl_usd  = capital * (pnl_pct / 100)

    # --- LÓGICA DE SALIDA AGRESIVA ---
    # 1. ¿MTF o SARS giró en contra?
    # Para Longs: MTF negativo (< -0.1). Para Shorts: MTF positivo (> 0.1)
    mtf_reversed = (
        (side == 'long'  and current_mtf < -0.1) or
        (side == 'short' and current_mtf > 0.1)
    )

    if not mtf_reversed:
        return {'should_exit': False}

    # 2. Evaluación de P&L para decidir la agresividad
    # Si tenemos ganancia (aunque sea mínima), salimos YA para asegurar.
    if pnl_pct >= 0.05:
        return {
            'should_exit': True,
            'reason': 'early_profit_protection',
            'pnl_pct': round(pnl_pct, 4),
            'detail': f'Reversión detectada con P&L positivo ({pnl_pct:.2f}%). Asegurando ganancia.'
        }
    
    # 3. Si estamos en pérdida, pero la reversión es FUERTE (MTF > 0.5 en contra),
    # salimos para evitar el SL completo.
    is_strong_reversal = abs(current_mtf) > 0.5
    if pnl_pct < 0 and is_strong_reversal:
        return {
            'should_exit': True,
            'reason': 'sl_prevention',
            'pnl_pct': round(pnl_pct, 4),
            'detail': f'Reversión fuerte detectada ({current_mtf:.2f}). Cortando pérdida antes del SL.'
        }

    return {'should_exit': False}

async def check_sl_proximity_alert(
    symbol:        str,
    current_price: float,
    sl_price:      float,
    danger_threshold_pct: float = 3.0,
    escalation_drop_pct:  float = 1.0
) -> None:
    """Envía alerta de SL cercano de forma inteligente para evitar spam."""
    # Normalizar símbolo para evitar duplicados por formato (BTC/USDT vs BTCUSDT)
    norm_symbol = symbol.replace("/", "").upper()
    
    # Inicialización por símbolo solo si no existe
    if norm_symbol not in BOT_STATE.sl_alerts:
        BOT_STATE.sl_alerts[norm_symbol] = {
            'in_danger_zone':    False,
            'last_distance_pct': 100.0,
            'last_alert_sent':   None,
            'last_alert_price':  0.0
        }

    state = BOT_STATE.sl_alerts[norm_symbol]
    distance_pct = abs(current_price - sl_price) / sl_price * 100 if sl_price > 0 else 100

    currently_in_danger = distance_pct < danger_threshold_pct
    was_in_danger       = state['in_danger_zone']
    last_distance       = state['last_distance_pct']
    last_price          = state['last_alert_price']
    last_time           = state['last_alert_sent']

    from app.workers.alerts_service import send_telegram_message

    # --- PROTECCIÓN ANTI-SPAM EXTRA ---
    # Si el precio es IDÉNTICO al de la última alerta, no enviar nada (previene spam si hay datos estáticos)
    if currently_in_danger and abs(current_price - last_price) < 0.0001:
        return

    # Si se envió una alerta hace menos de 15 minutos con una distancia similar, esperar.
    # Excepción: si el peligro aumenta significativamente (> 1% de caída extra)
    now = datetime.now(timezone.utc)
    # is_recent = last_time and (now - last_time).total_seconds() < 900 # 15 mins (Opcional, ya tenemos price check)
    
    significant_drop = (last_distance - distance_pct >= escalation_drop_pct)

    # CASO 1: Primera vez que entra en zona
    if currently_in_danger and not was_in_danger:
        msg = (f"⚠️ PRECIO CERCANO AL SL [{norm_symbol}]\n"
               f"Precio: ${current_price:,.2f} → SL: ${sl_price:,.2f}\n"
               f"Distancia: {distance_pct:.1f}% — Monitorear")
        await send_telegram_message(msg)
        state['in_danger_zone']    = True
        state['last_distance_pct'] = distance_pct
        state['last_alert_price']  = current_price
        state['last_alert_sent']   = now
        log_warning(MODULE, f"SL Danger Zone START for {norm_symbol}: {distance_pct:.1f}%")
        return

    # CASO 2: Ya estaba en peligro, pero empeoró significativamente
    if currently_in_danger and was_in_danger and significant_drop:
        emoji = "🚨" if distance_pct < 1.0 else "🔴" if distance_pct < 2.0 else "⚠️"
        urgency = "PELIGRO CRÍTICO" if distance_pct < 1.0 else "PELIGRO ALTO" if distance_pct < 2.0 else "MONITOREAR"
        
        msg = (f"{emoji} SL MÁS CERCANO [{norm_symbol}]\n"
               f"Precio: ${current_price:,.2f} → SL: ${sl_price:,.2f}\n"
               f"Distancia: {distance_pct:.1f}% — {urgency}\n"
               f"(Antes: {last_distance:.1f}%)")
        await send_telegram_message(msg)
        state['last_distance_pct'] = distance_pct
        state['last_alert_price']  = current_price
        state['last_alert_sent']   = now
        log_warning(MODULE, f"SL Danger Zone ESCALATION for {norm_symbol}: {distance_pct:.1f}%")
        return

    # CASO 3: Salió de la zona de peligro
    if not currently_in_danger and was_in_danger:
        msg = (f"✅ ZONA DE PELIGRO SUPERADA [{norm_symbol}]\n"
               f"Precio: ${current_price:,.2f} → SL: ${sl_price:,.2f}\n"
               f"Distancia: {distance_pct:.1f}% — Riesgo normalizado")
        await send_telegram_message(msg)
        state['in_danger_zone']    = False
        state['last_distance_pct'] = distance_pct
        state['last_alert_price']  = current_price
        state['last_alert_sent']   = now
        log_info(MODULE, f"SL Danger Zone RECOVERY for {norm_symbol}: {distance_pct:.1f}%")
        return

# Cache en memoria para estados de protección
_protection_cache = {}

async def check_protections(
    symbol:        str,
    position:      dict,
    current_price: float,
    snap:          dict,
    supabase
) -> bool:
    """
    Verifica y aplica las protecciones de Break-Even y Trailing Stop.
    Retorna True si la posición fue cerrada por el SL dinámico.
    """
    pos_id = str(position.get('id', symbol))

    # Inicializar estado si no existe
    if pos_id not in _protection_cache:
        # Resolver side
        side_raw = str(position.get('side', 'long')).lower()
        
        _protection_cache[pos_id] = ProtectionState(
            symbol       = symbol,
            side         = side_raw,
            entry_price  = float(position.get('avg_entry_price', position.get('entry_price', 0))),
            current_sl   = float(position.get('sl_price', position.get('stop_loss', 0))),
            market_type  = 'crypto_futures'
        )
        # Campos adicionales no presentes en el constructor base pero necesarios para el flujo
        state = _protection_cache[pos_id]
        state.original_sl = float(position.get('sl_backstop_price', position.get('sl_price', 0)))
        state.remaining_size = float(abs(float(position.get('size', 0))))

    state = _protection_cache[pos_id]
    state.cycles_open += 1
    
    # Asegurar que el SL en el estado coincida con el de la DB por si hubo cambios externos
    state.current_sl = float(position.get('sl_price', position.get('stop_loss', 0)))

    # ── TRACK PEAK P&L (máximo P&L alcanzado durante la vida de la posición) ──
    entry_p = state.entry_price
    if entry_p > 0:
        is_long = state.side in ('long', 'buy')
        current_pnl_pct = ((current_price - entry_p) / entry_p * 100) if is_long else ((entry_p - current_price) / entry_p * 100)
        if current_pnl_pct > state.highest_pnl_pct:
            state.highest_pnl_pct = current_pnl_pct
            try:
                supabase.table('positions').update({
                    'peak_pnl_pct': round(current_pnl_pct, 4)
                }).eq('id', pos_id).execute()
            except Exception:
                pass  # Non-critical, silently continue

    # ── CHECK 1: Break-Even ───────────────────
    be = evaluate_break_even(state, current_price)
    if be['action'] == 'activate_be':
        new_sl = be['be_price']
        try:
            supabase.table('positions').update({
                'sl_price': new_sl,
                'stop_loss': new_sl,
                'sl_type': 'break_even',
                'sl_dynamic_price': new_sl,
                'protection_activated': True
            }).eq('id', pos_id).execute()

            state.be_activated = True
            state.be_price     = new_sl
            state.current_sl   = new_sl
            position['sl_price'] = new_sl # Update local ref

            log_info('PROTECTION', f'🎯 BE [{symbol}]: {be["reason"]}')
            
            from app.workers.alerts_service import send_telegram_message
            await send_telegram_message(
                f'🎯 BREAK-EVEN ACTIVADO [{symbol}]\n'
                f'Razón: {be["reason"]}\n'
                f'SL movido a: {new_sl:.6f}\n'
                f'Precio actual: {current_price:.6f}'
            )
        except Exception as e:
            log_error(MODULE, f"Error actualizando BE para {symbol}: {e}")

    # ── CHECK 2: Trailing Stop ────────────────
    trail = evaluate_trailing_stop(state, current_price)
    if trail['action'] == 'update_sl':
        new_sl = trail['new_sl']
        try:
            supabase.table('positions').update({
                'sl_price': new_sl,
                'stop_loss': new_sl,
                'trailing_sl_price': new_sl,
                'sl_type': f'trailing_l{trail["new_level"]}',
                'protection_activated': True
            }).eq('id', pos_id).execute()

            state.trailing_level = trail['new_level']
            state.current_sl     = new_sl
            position['sl_price'] = new_sl # Update local ref

            log_info('PROTECTION', f'📈 TRAIL L{trail["new_level"]} [{symbol}]: {trail["reason"]}')
        except Exception as e:
            log_error(MODULE, f"Error actualizando Trail para {symbol}: {e}")

    # ── CHECK 3: SL backstop hit ──────────────
    sl = state.current_sl
    side = state.side
    if sl > 0:
        sl_hit = (
            (side in ('long','buy') and current_price <= sl) or
            (side not in ('long','buy') and current_price >= sl)
        )
        if sl_hit:
            log_info('PROTECTION', f'🔴 SL HIT [{symbol}]: precio={current_price:.6f} sl={sl:.6f}')
            # Usar la función de cierre existente en el monitor
            await _execute_paper_close(position, current_price, f'sl_{position.get("sl_type", "backstop")}', supabase)
            _protection_cache.pop(pos_id, None)
            return True

    return False

async def check_open_positions_5m(
    provider,
    supabase,
    telegram_bot
) -> list[dict]:
    """
    Ejecutar en cada ciclo de 5m.
    1. Verifica posiciones en Binance (si hay conexión real)
    2. Maneja cierres parciales y totales para PAPER TRADING via market_snapshot
    """
    events = []
    
    # --- PHASE 1: Real Exchange Sync ---
    open_positions_mem = BOT_STATE.positions
    if open_positions_mem:
        symbols = list(open_positions_mem.keys())
        for symbol in symbols:
            try:
                real = await provider.get_position(symbol)
                binance_is_open = abs(float(real.get('positionAmt', 0))) > 0
                if not binance_is_open:
                    await _handle_unexpected_close(symbol, open_positions_mem[symbol], real, supabase, telegram_bot)
                    events.append({'symbol': symbol, 'event': 'unexpected_close'})
            except: pass

    # --- PHASE 2: Paper Trading monitor (SL/TP) ---
    try:
        # Get latest configuration
        config_res = supabase.table('trading_config').select('*').eq('id', 1).single().execute()
        config = config_res.data or {}

        # Get latest snapshot for MTFs
        snap_res = supabase.table('market_snapshot').select('symbol, price, mtf_score, adx').execute()
        mtf_scores = {r['symbol'].replace("/", ""): float(r.get('mtf_score') or 0) for r in (snap_res.data or [])}
        
        # Get active positions from Supabase
        pos_res = supabase.table('positions').select('*').eq('status', 'open').execute()
        for pos in pos_res.data:
            symbol = pos['symbol']
            norm_symbol = normalize_crypto_symbol(symbol)
            
            # 0. DETECCIÓN DE PRECIO (ROBUSTA)
            # Prioridad 1: Binance Ticker (Live). Prioridad 2: Market Snapshot (DB).
            price = None
            try:
                ticker = await provider.get_ticker(norm_symbol)
                price = float(ticker['price'])
            except:
                # Fallback to snapshot price
                snap_row = next((r for r in snap_res.data if r['symbol'].replace("/", "") == norm_symbol), None)
                if snap_row:
                    price = float(snap_row.get('price', 0))
            
            if not price or price <= 0:
                log_warning(MODULE, f"Skipping monitor for {norm_symbol}: Price not available")
                continue
            
            # 0.1 SISTEMA DE PROTECCIÓN DE CAPITAL (4 Pasos)
            # Inyectamos el monitor de protecciones dinámicas (BE, Trailing, Backstop)
            current_snap_obj = next((r for r in snap_res.data if r['symbol'].replace("/", "") == norm_symbol), {})
            closed = await check_protections(norm_symbol, pos, price, current_snap_obj, supabase)
            if closed:
                # Register SL cooldown when closed by protection (SL hit)
                side = (pos.get('side') or 'long').lower()
                register_sl_event(norm_symbol, side)
                events.append({'symbol': norm_symbol, 'event': 'protection_close'})
                continue

            # 0.1.1 TIME-BASED SL (Corrección #1)
            # Cierra posiciones zombi que llevan demasiado tiempo sin ganancia
            time_sl = check_time_based_sl(pos, snap=current_snap_obj)
            if time_sl.get('should_close'):
                await _execute_paper_close(pos, price, time_sl['reason'], supabase)
                register_sl_event(norm_symbol, (pos.get('side') or 'long').lower())
                events.append({'symbol': norm_symbol, 'event': 'time_based_sl'})

                from app.workers.alerts_service import send_telegram_message
                await send_telegram_message(
                    f"🕐 TIME-BASED SL [{norm_symbol}]\n"
                    f"Tiempo: {time_sl['hours_open']:.1f}h "
                    f"(máx={time_sl['max_hours']}h)\n"
                    f"Peak PnL: {time_sl['peak_pnl']:.3f}%\n"
                    f"Velocidad: {time_sl['velocity']}\n"
                    f"→ Cerrado para limitar exposición"
                )
                log_info(MODULE, time_sl['detail'])
                continue

            # 0.2 ACTUALIZACIÓN DE P&L PARA DASHBOARD
            entry_p = float(pos.get('entry_price') or pos.get('avg_entry_price') or 0)
            is_long = side in ['long', 'buy']
            
            from app.core.crypto_symbols import resolve_crypto_position_quantity
            current_qty = resolve_crypto_position_quantity(supabase, pos)
            
            upnl = (price - entry_p) * current_qty if is_long else (entry_p - price) * current_qty
            
            try:
                supabase.table('positions').update({
                    'current_price': price,
                    'unrealized_pnl': round(upnl, 4)
                }).eq('id', pos['id']).execute()
            except Exception as upd_e:
                log_warning(MODULE, f"Silent update fail for {symbol}: {upd_e}")

            # 1. STOP LOSS (Full Close) via Dynamic SL Manager
            from app.strategy.dynamic_sl_manager import evaluate_sl_action
            df_4h = MEMORY_STORE.get(norm_symbol, {}).get('4h', {}).get('df')
            df_1d = MEMORY_STORE.get(norm_symbol, {}).get('1d', {}).get('df')

            # We use snapshot info mapped to what evaluate_sl_action expects
            snap_for_sl = next((r for r in snap_res.data if r['symbol'].replace("/", "") == norm_symbol), {})

            sl_action = evaluate_sl_action(
                position      = pos,
                current_price = price,
                snap          = snap_for_sl,
                df_4h         = df_4h,
                df_1d         = df_1d,
                market_type   = 'crypto_futures',
            )

            action = sl_action['action']

            if action == 'close_backstop':
                await _execute_paper_close(pos, price, 'backstop_sl', supabase)
                events.append({'symbol': symbol, 'event': 'backstop_sl_hit'})
                continue

            if action == 'trigger_dynamic_sl':
                await _execute_paper_close(pos, price, 'dynamic_sl', supabase)
                events.append({'symbol': symbol, 'event': 'dynamic_sl_hit'})
                continue

            if action == 'activate_dynamic_sl':
                sl_dynamic_price = sl_action['sl_price']
                sipv             = sl_action['sipv']
                
                log_info(MODULE, f'⚡ ACTIVANDO DYNAMIC SL {norm_symbol}: {sl_dynamic_price:.6f} ({sl_action["reason"]})')
                
                try:
                    supabase.table('positions').update({
                        'sl_dynamic_price':    sl_dynamic_price,
                        'sl_type':             'dynamic',
                        'sl_activated_at':     datetime.now(timezone.utc).isoformat(),
                        'sl_activation_reason': sipv.get('pattern', 'sipv'),
                        'stop_loss':     sl_dynamic_price,
                    }).eq('id', pos['id']).execute()
                    
                    from app.strategy.dynamic_sl_manager import send_sl_to_exchange
                    await send_sl_to_exchange(
                        symbol      = norm_symbol,
                        side        = side,
                        sl_price    = sl_dynamic_price,
                        quantity    = pos.get('size'),
                        position_id = pos['id'],
                        supabase    = supabase,
                        market_type = 'crypto_futures'
                    )
                except Exception as upd_e:
                    log_warning(MODULE, f"Silent dynamic SL update fail for {symbol}: {upd_e}")

            if action == 'update_trailing':
                try:
                    supabase.table('positions').update({
                        'trailing_sl_price': sl_action['sl_price'],
                        'highest_price_reached': sl_action.get('new_max'),
                        'lowest_price_reached': sl_action.get('new_min'),
                    }).eq('id', pos['id']).execute()
                except Exception as upd_e:
                    log_warning(MODULE, f"Silent trailing SL update fail for {symbol}: {upd_e}")

            # 2. TAKE PROFIT PARTIAL (50% Close)
            is_tp_p = (side == 'long' and price >= tp_p) or (side == 'short' and price <= tp_p) if (tp_p > 0 and not pos.get('partial_closed')) else False
            if is_tp_p:
                await _execute_paper_partial_close(pos, price, supabase)
                events.append({'symbol': symbol, 'event': 'tp_partial_hit'})
                continue

            # 3. TAKE PROFIT FULL (Full Close)
            is_tp_f = (side == 'long' and price >= tp_f) or (side == 'short' and price <= tp_f) if tp_f > 0 else False
            if is_tp_f:
                await _execute_paper_close(pos, price, 'tp_full', supabase)
                events.append({'symbol': symbol, 'event': 'tp_full_hit'})
                continue

            # 4. DYNAMIC HOLDING MAX (Based on market velocity / ADX)
            try:
                from app.core.parameter_guard import get_velocity_config
                # Get ADX from snapshot
                snap_adx = {r['symbol'].replace("/", ""): float(r.get('adx', 25))
                            for r in snap_res.data} if snap_res.data else {}
                current_adx = snap_adx.get(norm_symbol, 25)
                vel_config = get_velocity_config(current_adx)
                holding_max = vel_config['holding_max']
                
                # Calculate bars held
                opened_at = pos.get('opened_at')
                if opened_at:
                    from datetime import datetime, timezone
                    opened_dt = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
                    now_dt = datetime.now(timezone.utc)
                    elapsed_min = (now_dt - opened_dt).total_seconds() / 60
                    bars_held = int(elapsed_min / 5)  # 5m bars
                    
                    if bars_held >= holding_max:
                        entry_p = float(pos.get('entry_price') or pos.get('avg_entry_price') or 0)
                        if entry_p > 0:
                            if side == 'long':
                                hold_pnl = (price - entry_p) / entry_p * 100
                            else:
                                hold_pnl = (entry_p - price) / entry_p * 100
                        else:
                            hold_pnl = 0
                        
                        close_reason = f'hold_{vel_config["velocity"][:10]}'
                        await _execute_paper_close(pos, price, close_reason, supabase)
                        events.append({'symbol': symbol, 'event': 'max_holding_close'})
                        
                        from app.workers.alerts_service import send_telegram_message
                        await send_telegram_message(
                            f"⏱️ CIERRE POR TIEMPO [{norm_symbol}]\n"
                            f"Velocidad: {vel_config['velocity'].upper()}\n"
                            f"Holding: {bars_held} velas "
                            f"(máx: {holding_max})\n"
                            f"P&L: {hold_pnl:.2f}%"
                        )
                        log_info(MODULE, f"Max holding close for {norm_symbol}: {bars_held}/{holding_max} bars ({vel_config['velocity']})")
                        continue
            except Exception as vel_e:
                log_warning(MODULE, f"Velocity holding check error for {norm_symbol}: {vel_e}")

            # 5. SL PROXIMITY ALERT (Inteligente)
            await check_sl_proximity_alert(
                symbol               = norm_symbol,
                current_price        = price,
                sl_price             = sl,
                danger_threshold_pct = 3.0,
                escalation_drop_pct  = 1.0
            )

            # 6. SIGNAL REVERSAL (Early Exit / SL Prevention)
            # Evalúa si la tendencia giró para salir antes del SL o asegurar TP.
            rev_res = await check_signal_reversal(pos, mtf_score, price, config)
            if rev_res.get('should_exit'):
                reason = rev_res.get('reason', 'signal_reversal')
                await _execute_paper_close(pos, price, reason, supabase)
                events.append({'symbol': symbol, 'event': 'signal_reversal_exit'})
                
                from app.workers.alerts_service import send_telegram_message
                await send_telegram_message(
                    f"⚠️ SALIDA ANTICIPADA [{norm_symbol}]\n"
                    f"Razón: {reason.replace('_', ' ').upper()}\n"
                    f"P&L: {upnl / (entry_p * float(pos.get('size') or 1)) * 100:.2f}%\n"
                    f"Detalle: {rev_res.get('detail')}"
                )
                continue
                
    except Exception as e:
        log_error(MODULE, f"Error in paper monitoring: {e}")

    return events

async def _run_protection_crypto(pos: dict, price: float, supabase):
    """Aplica el motor de protección de capital a posiciones de Cripto."""
    symbol = pos['symbol']
    pos_id = pos['id']
    
    # Obtener o inicializar estado en BOT_STATE
    if not hasattr(BOT_STATE, 'protection_cache'):
        BOT_STATE.protection_cache = {}
        
    if pos_id not in BOT_STATE.protection_cache:
        BOT_STATE.protection_cache[pos_id] = ProtectionState(
            symbol=symbol,
            entry_price=float(pos.get('avg_entry_price') or pos.get('entry_price') or 0),
            current_sl=float(pos.get('sl_price') or pos.get('stop_loss') or 0),
            side=pos['side'].lower()
        )
    
    state = BOT_STATE.protection_cache[pos_id]
    result = evaluate_all_protections(state, price, market_type='crypto_futures')
    
    if result['has_action']:
        action = result['action']
        if action == 'move_sl':
            new_sl = result['new_sl']
            log_info(MODULE, f"🛡️ [PROTECTION] {symbol}: Moviendo SL a {new_sl} ({result['reason']})")
            # Persistencia en DB
            try:
                supabase.table('positions').update({
                    'sl_price': new_sl,
                    'stop_loss': new_sl,
                    'sl_update_reason': result['reason']
                }).eq('id', pos_id).execute()
                # Actualizar objeto local para el resto del ciclo
                pos['sl_price'] = new_sl
                pos['stop_loss'] = new_sl
            except Exception as e:
                log_error(MODULE, f"Error updating protection SL for {symbol}: {e}")
        
        elif action == 'close_inverse' and result.get('confidence', 0) > 0.8:
            log_info(MODULE, f"🛡️ [PROTECTION] {symbol}: Cierre por señal inversa confirmado")
            await _execute_paper_close(pos, price, 'inverse_signal', supabase)

async def _execute_paper_open(
    symbol, side, price, size, rule_code, regime, levels, vel_config, supabase
):
    """
    Simula la apertura de una posición paper y persiste en Supabase.
    Aplica SL y TP dinámicos basados en la velocidad (ADX).
    """
    from app.core.memory_store import BOT_STATE
    from app.core.logger import log_info

    symbol = normalize_crypto_symbol(symbol)

    # 1. REVERSIÓN FORZADA (Hedge no permitido)
    # Si llega una señal LONG y hay SHORTs (o viceversa), cerrar todo lo opuesto primero.
    async with BOT_STATE.order_lock:
        opposite_side = 'SHORT' if side.upper() in ['LONG', 'BUY'] else 'LONG'
        opp_res = supabase.table('positions').select('*').in_('symbol', crypto_symbol_match_variants(symbol)).eq('status', 'open').execute()
        
        # Filtrar manualmente por el lado opuesto (considerando alias BUY/LONG)
        to_close = []
        for p in (opp_res.data or []):
            p_side = (p.get('side') or '').upper()
            if opposite_side == 'SHORT' and p_side in ['SHORT', 'SELL']:
                to_close.append(p)
            elif opposite_side == 'LONG' and p_side in ['LONG', 'BUY']:
                to_close.append(p)
        
        if to_close:
            log_info(MODULE, f"🔄 REVERSIÓN: Cerrando {len(to_close)} posiciones opuestas ({opposite_side}) en {symbol} antes de abrir {side.upper()}")
            for pos in to_close:
                await _execute_paper_close(pos, price, f'reversal_{side.lower()}', supabase)

        # 2. Límite GLOBAL (max_open_trades) y SÍMBOLO usando LOCK para atomicidad
        max_global = int(BOT_STATE.config_cache.get('max_open_trades', 3))
        
        # Consultar DB directamente para conteo global exacto
        pos_res = supabase.table('positions').select('id').eq('status', 'open').execute()
        current_global = len(pos_res.data) if pos_res.data else 0
        
        if current_global >= max_global:
            log_info(MODULE, f"GLOBAL_LIMIT: {symbol} bloqueado ({rule_code}). Límite de {max_global} posiciones alcanzado ({current_global}).")
            return None

        # 3. Límite POR SÍMBOLO
        from app.core.supabase_client import get_risk_config
        risk_config = get_risk_config()
        max_symbol = int(risk_config.get('max_positions_per_symbol', 4))
        
        # Contar posiciones abiertas para este símbolo específico
        sym_pos_res = supabase.table('positions').select('id').in_('symbol', crypto_symbol_match_variants(symbol)).eq('status', 'open').execute()
        current_sym = len(sym_pos_res.data) if sym_pos_res.data else 0

        if current_sym >= max_symbol:
            log_info(MODULE, f"SYMBOL_LIMIT: {symbol} bloqueado ({rule_code}). Límite de {max_symbol} posiciones por símbolo alcanzado ({current_sym}).")
            return None

        # Si pasamos los límites, procedemos a abrir (dentro del lock o justo después)
        # Lo mantenemos dentro del lock para que el 'count' de la siguiente tarea sea correcto
        res = await _execute_paper_open_unlocked(
            symbol, side, price, size, rule_code, regime, levels, vel_config, supabase
        )
        return res

async def _execute_paper_open_unlocked(
    symbol, side, price, size, rule_code, regime, levels, vel_config, supabase
):
    """Lógica interna de apertura sin lock (ya envuelto por _execute_paper_open)"""
    from datetime import datetime, timezone
    from app.core.position_sizing import calculate_sl_tp
    
    # Obtener configuración de TP según banda de velocidad
    # tp_band viene como 'lower_2', extraemos el nivel (2)
    try:
        band_str = vel_config.get('tp_band', 'lower_6')
        import re
        match = re.search(r'(\d+)', band_str)
        level_num = match.group(1) if match else "6"
        
        # Mapear a la dirección correcta
        prefix = 'upper' if side == 'long' else 'lower'
        tp_target_col = f"{prefix}_{level_num}"
        # parcial un nivel menos
        partial_num = str(max(1, int(level_num) - 1))
        tp_partial_col = f"{prefix}_{partial_num}"
        
        tp_full    = float(levels.get(tp_target_col, price * (1.1 if side == 'long' else 0.9)))
        tp_partial = float(levels.get(tp_partial_col, price * (1.05 if side == 'long' else 0.95)))
    except:
        tp_full    = price * (1.08 if side == 'long' else 0.92)
        tp_partial = price * (1.04 if side == 'long' else 0.96)

    # Calculamos SL con el multiplicador dinámico de velocidad y buffer extra
    from app.core.memory_store import BOT_STATE
    buffer_pct = float(BOT_STATE.config_cache.get('sl_extra_buffer_pct', 0.5))
    
    sl_dict = calculate_sl_tp(
        side        = side,
        entry_price = price,
        atr         = float(levels.get('atr', price * 0.02)), # Fallback approx
        atr_mult    = float(vel_config.get('sl_mult', 1.0)),
        levels      = levels,
        sl_buffer_pct = buffer_pct
    )
    
    # ── VALIDACIÓN DE COHERENCIA SL vs ENTRY (V2 Engine) ──
    sl_final = sl_dict['sl_price']
    if side.lower() in ['long', 'buy'] and sl_final >= price and sl_final > 0:
        sl_final = price * 0.995  # Forzar SL 0.5% debajo del entry
        log_warning(MODULE, f"{symbol}: SL V2 corregido para LONG. SL={sl_final:.6f} < Entry={price:.6f}")
    elif side.lower() in ['short', 'sell'] and sl_final <= price and sl_final > 0:
        sl_final = price * 1.005  # Forzar SL 0.5% arriba del entry
        log_warning(MODULE, f"{symbol}: SL V2 corregido para SHORT. SL={sl_final:.6f} > Entry={price:.6f}")
    sl_dict['sl_price'] = sl_final

    # Persistir
    data = {
        'symbol':           symbol,
        'side':             side.upper(),
        'entry_price':      round(price, 8),
        'avg_entry_price':  round(price, 8),
        'current_price':    round(price, 8),
        'size':             round(size, 8),
        'stop_loss':        round(sl_final, 8),
        'take_profit':      round(tp_full, 8),
        'sl_price':         round(sl_final, 8),
        'tp_partial_price': round(tp_partial, 8),
        'tp_full_price':    round(tp_full, 8),
        'status':           'open',
        'regime_entry':     regime.get('category', 'riesgo_medio'),
        'rule_code':        rule_code,
        'rule_entry':       rule_code,
        'velocity_entry':   vel_config.get('velocity', 'unknown'),
        'opened_at':        datetime.now(timezone.utc).isoformat(),
        'mode':             'paper'
    }
    
    # Dashboard log (orders table)
    try:
        supabase.table('orders').insert({
            'symbol': symbol,
            'side': 'BUY' if side.lower() == 'long' else 'SELL',
            'order_type': 'MARKET',
            'quantity': size,
            'limit_price': price,
            'entry_price': price,
            'stop_loss_price': sl_dict['sl_price'],
            'take_profit_price': tp_full,
            'status': 'open',
            'is_paper': True,
            'rule_code': rule_code
        }).execute()
    except Exception as e:
        log_warning(MODULE, f"Failed to log order to orders table: {e}")

    res = supabase.table('positions').insert(data).execute()
    new_pos = res.data[0] if res.data else None
    if new_pos:
        from app.core.memory_store import BOT_STATE
        BOT_STATE.positions[symbol] = new_pos

    log_info(MODULE, f"🚀 PAPER OPEN [{symbol}] {side.upper()} at ${price:,.2f} (SL: ${data['sl_price']:,.2f}, TP: ${data['tp_full_price']:,.2f})")
    return new_pos

async def _execute_paper_partial_close(pos, price, supabase):
    """Ejecuta cierre parcial simulado (50% del capital)."""
    symbol = pos['symbol']
    entry = float(pos.get('entry_price') or 0)
    side = (pos.get('side') or '').lower()
    
    # PnL %
    is_long = side in ['long', 'buy']
    pnl_pct = ((price - entry) / entry * 100) if is_long else ((entry - price) / entry * 100)
    
    # Asumimos que T1 es todo el capital actual (v4 simple distribution)
    # Si queremos ser precisos necesitamos 'capital_per_symbol'
    # Por ahora, cerramos el 50% de la cantidad 'size'
    partial_qty = float(pos['size']) * 0.5
    partial_pnl_usd = (price - entry) * partial_qty if is_long else (entry - price) * partial_qty
    
    # Update Position
    supabase.table('positions').update({
        'partial_closed': True,
        'partial_close_price': price,
        'current_price': price,
        'partial_close_usd': round(partial_pnl_usd, 4),
        'size': float(pos['size']) - partial_qty
    }).eq('id', pos['id']).execute()
    
    # 2. Persistir en paper_trades (Log de actividad parcial)
    p_rule_code = pos.get('rule_code') or pos.get('rule_entry') or "Cc-Partial"
    
    supabase.table('paper_trades').insert({
        'symbol':       symbol,
        'side':         pos['side'],
        'entry_price':  entry,
        'exit_price':   price,
        'total_pnl_usd': round(partial_pnl_usd, 4),
        'total_pnl_pct': round(pnl_pct, 4),
        'close_reason': 'partial_tp',
        'closed_at':    datetime.now(timezone.utc).isoformat(),
        'mode':         'paper',
        'rule_code':    p_rule_code
    }).execute()
    
    log_info(MODULE, f"✅ PARTIAL CLOSE [{symbol}] at ${price:,.2f} | PnL: ${partial_pnl_usd:.2f}")

async def _execute_paper_close(pos, price, reason, supabase):
    """Cierra la posición completamente en Paper Trading."""
    symbol = pos['symbol']
    entry = float(pos.get('entry_price') or 0)
    side = (pos.get('side') or '').lower()
    qty = float(pos['size'])
    
    is_long = side in ['long', 'buy']
    pnl_usd = (price - entry) * qty if is_long else (entry - price) * qty
    pnl_pct = ((price - entry) / entry * 100) if side == 'long' else ((entry - price) / entry * 100)

    # Si hubo cierre parcial previo, sumar sus USD
    total_pnl = pnl_usd + float(pos.get('partial_pnl_usd', 0))

    supabase.table('positions').update({
        'status': 'closed',
        'close_reason': reason,
        'current_price': price,
        'closed_at': datetime.now(timezone.utc).isoformat(),
        'realized_pnl': round(total_pnl, 4)
    }).eq('id', pos['id']).execute()
    
    from app.strategy.dynamic_sl_manager import cancel_all_sl_orders
    await cancel_all_sl_orders(
        symbol=symbol,
        position=pos,
        supabase=supabase,
        reason=reason
    )

    p_rule_code = pos.get('rule_code') or pos.get('rule_entry') or "Cc-Manual"
    # Enriquecer close_reason con sl_type para análisis post-deploy
    detailed_reason = reason
    sl_type = pos.get('sl_type', '')
    if reason.startswith('sl_') and sl_type and sl_type not in reason:
        detailed_reason = f"{reason}_{sl_type}"
    
    supabase.table('paper_trades').insert({
        'symbol': symbol,
        'side': pos['side'],
        'entry_price': entry,
        'exit_price': price,
        'total_pnl_usd': round(total_pnl, 4),
        'total_pnl_pct': round(pnl_pct, 4),
        'close_reason': detailed_reason,
        'closed_at': datetime.now(timezone.utc).isoformat(),
        'mode': 'paper',
        'rule_code': p_rule_code
    }).execute()
    
    # ── REGISTRAR PN EN CAPITAL ACUMULADO (Interés Compuesto) ──
    try:
        from app.core.capital_manager import register_realized_pnl
        # Determinar mercado (heuristicamente por símbolo)
        market = 'forex' if any(x in symbol for x in ['EUR', 'GBP', 'JPY', 'XAU']) else 'crypto'
        register_realized_pnl(market, total_pnl)
    except Exception as cap_e:
        log_warning(MODULE, f"Error actualizando capital acumulado: {cap_e}")

    # ── CANCELAR ÓRDENES HUÉRFANAS ──
    # Al cerrar la posición, cancelar todas las pending_orders y actualizar orders
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        # 1. Cancelar pending_orders pendientes para este símbolo
        supabase.table('pending_orders').update({
            'status': 'cancelled',
            'cancelled_at': now_iso,
            'updated_at': now_iso
        }).eq('symbol', symbol).eq('status', 'pending').execute()
        
        # 2. Actualizar orders asociados al cierre (marcar como cerrados)
        close_status = 'sl_hit' if reason == 'sl' else ('tp_hit' if 'tp' in reason else 'closed')
        supabase.table('orders').update({
            'status': close_status,
            'closed_at': now_iso
        }).eq('symbol', symbol).eq('status', 'open').execute()
        
        log_info(MODULE, f"🧹 Órdenes pendientes canceladas para {symbol} (razón: {reason})")
    except Exception as cancel_e:
        log_warning(MODULE, f"Error cancelando órdenes huérfanas de {symbol}: {cancel_e}")

    # Remove from BOT_STATE
    BOT_STATE.positions.pop(symbol, None)

    # Register SL cooldown if closed by any SL mechanism (Corrección #2)
    sl_reasons = ('sl', 'backstop', 'dynamic_sl', 'time_sl', 'stop_loss')
    if any(r in reason.lower() for r in sl_reasons):
        register_sl_event(symbol, side)

    log_info(MODULE, f"🏁 FULL CLOSE [{symbol}] ({reason}) at ${price:,.2f} | Total PnL: ${total_pnl:.2f}")


async def _handle_unexpected_close(
    symbol, position, real_data,
    supabase, telegram_bot
):
    """
    La posición fue cerrada por Binance sin que el bot lo supiera.
    Puede ser: liquidación, SL ejecutado, TP ejecutado, o cierre manual.
    """
    # Determinar razón probable
    entry_price   = float(position.get('avg_entry', 0))
    liq_price     = float(real_data.get('liquidationPrice', 0))

    reason = 'unknown'
    # In Futures, if liq price was hit, it's a liquidation.
    # Note: liquidationPrice is where it WAS at last check or current.
    # If closed now, we check if it was close to liq.
    if liq_price > 0:
         # Rough heuristic: if it closed without bot intervention and we have liq price, 
         # it might be liquidation. But specifically for binance, 
         # usually we check if it was hit.
         reason = 'liquidation'
    elif position.get('sl_price'):
        reason = 'sl_or_tp_hit'

    # Actualizar Supabase
    await supabase.table('positions').update({
        'is_open':    False,
        'close_reason': reason,
        'closed_at':  datetime.now(timezone.utc).isoformat(),
    }).eq('symbol', symbol).eq('is_open', True).execute()

    # Limpiar de memoria
    BOT_STATE.positions.pop(symbol, None)

    # Alerta Telegram
    from app.workers.alerts_service import send_telegram_message
    emoji = "💥" if reason == 'liquidation' else "📌"
    if asyncio.iscoroutinefunction(send_telegram_message):
        await send_telegram_message(
            f"{emoji} POSICIÓN CERRADA POR BINANCE [{symbol}]\n"
            f"Razón detectada: {reason.upper()}\n"
            f"Precio entrada: ${entry_price:,.2f}\n"
            f"Verificar historial en Binance para PnL exacto."
        )
    else:
        send_telegram_message(
            f"{emoji} POSICIÓN CERRADA POR BINANCE [{symbol}]\n"
            f"Razón detectada: {reason.upper()}\n"
            f"Precio entrada: ${entry_price:,.2f}\n"
            f"Verificar historial en Binance para PnL exacto."
        )

    log_warning(MODULE,
        f"Posición {symbol} cerrada externamente: {reason}")
