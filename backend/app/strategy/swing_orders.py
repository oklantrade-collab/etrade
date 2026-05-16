import pandas as pd
from datetime import datetime, timezone, timedelta
from app.core.logger import log_info, log_error, log_warning, log_debug
from app.analysis.swing_detector import detect_basis_horizontal, find_current_band_zone, SWING_CONFIG, calculate_fall_maturity
from app.core.position_sizing import can_open_short, calculate_position_size
from app.core.parameter_guard import get_active_params
from app.workers.performance_monitor import send_telegram_message
from app.core.memory_store import BOT_STATE
import asyncio
from app.analysis.movement_classifier import (
    classify_movement
)
from app.analysis.smart_limit import (
    calculate_smart_limit_price
)
from app.core.crypto_symbols import crypto_symbol_match_variants

async def process_swing_orders_15m(symbol: str, df_15m: pd.DataFrame, df_4h: pd.DataFrame, snap: dict, provider, sb) -> None:
    """Ciclo de gestión de órdenes Swing cada 15m"""
    
    # --- VALIDACIÓN DE LÍMITE DE POSICIONES POR SÍMBOLO ---
    max_per_symbol = int(BOT_STATE.config_cache.get("max_positions_per_symbol", 4))

    try:
        # Contar posiciones abiertas en DB para este símbolo (atómico)
        variants = crypto_symbol_match_variants(symbol)
        open_res = sb.table('positions').select('id', count='exact').in_('symbol', variants).eq('status', 'open').limit(0).execute()
        num_open = open_res.count if open_res.count is not None else 999
        
        # Contar órdenes pendientes en DB para este símbolo
        pend_res = sb.table('pending_orders').select('id', count='exact').in_('symbol', variants).eq('status', 'pending').limit(0).execute()
        num_pending = pend_res.count if pend_res.count is not None else 0
        
        total_active = num_open + num_pending
        
        if total_active >= max_per_symbol:
            if num_pending == 0:
                log_debug('SWING_LIMITS', f"{symbol}: Límite alcanzado ({num_open}/{max_per_symbol}).")
                return
    except Exception as e:
        log_error('SWING_LIMITS', f"Error validando límites para {symbol}: {e}")

    # Continuar con la evaluación normal
    for df, timeframe in [(df_15m, '15m'), (df_4h, '4h')]:
        if df is None or df.empty:
            continue
            
        await process_swing_orders(symbol, timeframe, df, snap, sb)

async def process_swing_orders(
    symbol:   str,
    timeframe: str,
    df:       pd.DataFrame,
    snap:     dict,
    sb
):
    """
    Versión actualizada de swing_orders con
    Smart LIMIT Order Placement.
    """
    if timeframe != '15m':
        return 

    # --- PROACTIVE LIMIT CHECK ---
    try:
        max_per_symbol = int(BOT_STATE.config_cache.get("max_positions_per_symbol", 4))
        variants = crypto_symbol_match_variants(symbol)
        
        res_open = sb.table('positions').select('id', count='exact').in_('symbol', variants).eq('status', 'open').limit(0).execute()
        current_count = res_open.count if res_open.count is not None else 999
        
        if current_count >= max_per_symbol:
            log_info('SWING_LIMIT', f"{symbol}: Bloqueo proactivo. {current_count} posiciones abiertas (max {max_per_symbol}).")
            await cancel_swing_orders(symbol, timeframe='15m', reason='limit_reached_proactive', sb=sb)
            return
    except Exception as e:
        log_error('SWING_LIMIT', f"Error en proactive limit check para {symbol}: {e}")

    # --- CONSULTAR ÓRDENES PENDIENTES EXISTENTES ---
    try:
        res_pending = sb.table('pending_orders').select('direction, limit_price').eq('symbol', symbol).eq('status', 'pending').execute()
        existing_limits = {}
        if res_pending and res_pending.data:
            for p in res_pending.data:
                existing_limits[p['direction'].lower()] = float(p['limit_price'])
    except Exception as e:
        log_error('SWING_LIMIT', f"Error consultando órdenes pendientes existentes para {symbol}: {e}")
        existing_limits = {}

    for direction in ['long', 'short']:
        # 1. Clasificar movimiento
        movement = classify_movement(df=df, lookback=20)
        movement_type = movement['movement_type']

        if direction == 'long' and movement_type == 'descending' and movement['confidence'] > 0.80:
            continue
        if direction == 'short' and movement_type == 'ascending' and movement['confidence'] > 0.80:
            continue

        # 2. Calcular precio LIMIT óptimo
        limit_result = calculate_smart_limit_price(
            df=df, direction=direction, movement_type=movement_type, 
            lookback=50, margin_pct=0.0015
        )

        if not limit_result or not limit_result.get('limit_price') or limit_result['signal_quality'] == 'low':
            continue

        new_limit_price = float(limit_result['limit_price'])

        # 2.5 Evitar spam: Si ya existe una orden en la misma dirección y el precio es casi igual (< 0.5% de diff)
        if direction in existing_limits:
            old_price = existing_limits[direction]
            diff_pct = abs(new_limit_price - old_price) / old_price * 100
            if diff_pct < 0.5:
                log_debug('SMART_LIMIT', f"{symbol}/{direction}: Orden existente similar ({old_price:.4f} vs {new_limit_price:.4f}). Saltando.")
                continue

        # 3. Cancelar orden anterior (si el precio cambió significativamente o se había vencido)
        await cancel_swing_order(symbol=symbol, direction=direction, reason='smart_limit_recalculated', sb=sb)

        # 4. Calcular SL y TP
        entry = float(limit_result['limit_price'])
        basis = float(snap.get('basis', 0))
        
        if direction == 'long':
            sl_price = entry * (1 - 0.005)
            tp1_price = basis
            tp2_price = float(snap.get('upper_3', basis * 1.03))
        else:
            sl_price = entry * (1 + 0.005)
            tp1_price = basis
            tp2_price = float(snap.get('lower_3', basis * 0.97))

        # 5. Crear orden LIMIT
        ttl_hours = 2 if limit_result['distance_pct'] < 1.5 else 4
        await create_smart_limit_order(
            symbol=symbol, direction=direction, limit_price=entry,
            sl_price=sl_price, tp1_price=tp1_price, tp2_price=tp2_price,
            band_target=limit_result['band_target'], sizing_pct=limit_result['sizing_pct'],
            movement_type=movement_type, signal_quality=limit_result['signal_quality'],
            fib_zone_entry=limit_result['fib_zone_entry'], ttl_hours=ttl_hours, supabase=sb
        )

        log_info('SMART_LIMIT', f'{symbol}/{direction}: LIMIT ${entry:.4f} en {limit_result["band_target"]}')

        await send_telegram_message(
            f'📍 SMART LIMIT [{symbol}]\nDir: {direction.upper()}\nPrecio LIMIT: ${entry:.4f}\nCalidad: {limit_result["signal_quality"]}'
        )

async def cancel_swing_orders(symbol: str, timeframe: str = None, reason: str = 'recalculated', sb = None, direction: str = None, trade_type: str = None) -> None:
    data = {
        'status': 'cancelled',
        'cancelled_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'rejection_reason': (reason or "unknown")[:10]
    }
    query = sb.table('pending_orders').update(data).eq('symbol', symbol).eq('status', 'pending')
    if timeframe: query = query.eq('timeframe', timeframe)
    if direction: query = query.eq('direction', direction)
    if trade_type: query = query.eq('trade_type', trade_type)
    query.execute()

async def cancel_swing_order(symbol: str, direction: str, reason: str, sb):
    await cancel_swing_orders(symbol=symbol, direction=direction, reason=reason, sb=sb)

async def create_smart_limit_order(symbol, direction, limit_price, sl_price, tp1_price, tp2_price, band_target, sizing_pct, movement_type, signal_quality, fib_zone_entry, ttl_hours, supabase):
    # Truncate strings to avoid DB length errors (varchar 10)
    safe_trade_type = "smart_lim"  # 9 chars
    safe_movement = (movement_type or "unknown")[:10]
    
    new_order = {
        'symbol': symbol, 'direction': direction, 'order_type': 'limit', 'trade_type': safe_trade_type,
        'rule_code': 'SMART' if direction == 'long' else 'SMART_S',
        'limit_price': limit_price, 'sl_price': sl_price, 'tp1_price': tp1_price, 'tp2_price': tp2_price,
        'band_name': band_target, 'status': 'pending',
        'mode': 'paper' if BOT_STATE.config_cache.get("paper_trading", True) else 'real',
        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat(),
        'sizing_pct': sizing_pct, 'timeframe': '15m',
        'movement_type': safe_movement, 'signal_quality': signal_quality, 'fib_zone_entry': fib_zone_entry
    }
    supabase.table('pending_orders').insert(new_order).execute()

async def check_limit_order_execution(symbol: str, current_price: float, provider, sb) -> None:
    is_paper = BOT_STATE.config_cache.get("paper_trading", True)
    mode_filter = 'paper' if is_paper else 'real'
    
    pending = sb.table('pending_orders').select('*').eq('symbol', symbol).eq('status', 'pending').eq('mode', mode_filter).execute()
    if not pending.data: return

    for order in pending.data:
        limit_price = float(order['limit_price'])
        direction = order['direction']
        expires_at = order.get('expires_at')

        if expires_at:
            exp = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > exp:
                sb.table('pending_orders').update({'status': 'expired', 'cancelled_at': datetime.now(timezone.utc).isoformat()}).eq('id', order['id']).execute()
                continue

        price_hit = (direction == 'long' and current_price <= limit_price) or (direction == 'short' and current_price >= limit_price)
        if not price_hit: continue

        log_info('SWING', f'{symbol}: LIMIT EJECUTADO {direction.upper()} @ ${current_price:,.4f}')
        if is_paper:
            await execute_limit_order_paper(order=order, execution_price=current_price, sb=sb)
        else:
            await execute_limit_order_real(order=order, execution_price=current_price, binance_client=provider, sb=sb)

async def execute_limit_order_paper(order: dict, execution_price: float, sb) -> None:
    symbol = order['symbol']
    direction = order['direction']

    async with BOT_STATE.order_lock:
        try:
            # 1. Límite Global (Fail-Closed)
            max_global = int(BOT_STATE.config_cache.get('max_open_trades', 15))
            try:
                pos_res = sb.table('positions').select('id', count='exact').eq('status', 'open').limit(0).execute()
                current_global = pos_res.count if pos_res.count is not None else 0
            except Exception as e:
                log_error('SWING', f"Error consultando límite global: {e}")
                current_global = 999
            
            if current_global >= max_global:
                log_warning('SWING', f"GLOBAL_LIMIT: {symbol} bloqueado. {current_global}/{max_global}")
                return

            # 2. Límite por Símbolo
            max_symbol = int(BOT_STATE.config_cache.get('max_positions_per_symbol', 4))
            variants = crypto_symbol_match_variants(symbol)
            try:
                # Seleccionamos campos necesarios para DCA y Cool-down
                sym_pos_res = sb.table('positions').select('id, rule_code, opened_at, entry_price, side', count='exact').in_('symbol', variants).eq('status', 'open').execute()
                current_sym = sym_pos_res.count if sym_pos_res.count is not None else 0
                existing_data = sym_pos_res.data or []
                current_sym = max(current_sym, len(existing_data))
            except Exception as e:
                log_error('SWING', f"Error consultando límite símbolo: {e}")
                current_sym = 999
            
            if current_sym >= max_symbol:
                log_warning('SWING', f"SYMBOL_LIMIT: {symbol} bloqueado. {current_sym}/{max_symbol}")
                await cancel_swing_orders(symbol, timeframe=order.get('timeframe',''), reason='limit_reached', sb=sb)
                return
            
            # 2.1 DCA & COOL-DOWN PROTECTION (Basado en Forex logic)
            rule_code = order.get('rule_code', 'SWING')
            now_utc = datetime.now(timezone.utc)
            
            # 2.1.1 Spam Protection (Historial reciente cerrado o abierto)
            try:
                since = (now_utc - timedelta(minutes=15)).isoformat()
                hist = sb.table('positions').select('opened_at').in_('symbol', variants).eq('rule_code', rule_code).gte('opened_at', since).order('opened_at', desc=True).limit(1).execute()
                if hist.data:
                    log_warning('SWING', f"SPAM_BLOCK: {symbol} rule {rule_code} ejecutada hace menos de 15 min. Abortando.")
                    return
            except Exception as hist_e:
                log_warning('SWING', f"Error checking swing history: {hist_e}")

            # 2.1.2 DCA Price Improvement (Misma regla)
            same_rule_pos = [p for p in existing_data if p.get('rule_code') == rule_code]
            if same_rule_pos:
                last_pos = sorted(same_rule_pos, key=lambda x: x['opened_at'], reverse=True)[0]
                last_entry = float(last_pos.get('entry_price') or 0)
                
                # Para LONG: nuevo precio debe ser MENOR que el anterior (mejora costo)
                is_long = direction.lower() in ['long', 'buy']
                if is_long and execution_price >= last_entry:
                    log_warning('SWING', f"DCA_BLOCK: {symbol} LONG price {execution_price} >= {last_entry}. No mejora costo.")
                    return
                if not is_long and execution_price <= last_entry:
                    log_warning('SWING', f"DCA_BLOCK: {symbol} SHORT price {execution_price} <= {last_entry}. No mejora costo.")
                    return
        except Exception as limit_e:
            log_error('SWING', f"Error crítico validando límites: {limit_e}")
            return

        # 3. Reversión
        try:
            opposite_side = 'SHORT' if direction.lower() == 'long' else 'LONG'
            opp_res = sb.table('positions').select('*').in_('symbol', variants).eq('status', 'open').execute()
            to_close = [p for p in (opp_res.data or []) if (p.get('side') or '').upper() == opposite_side]
            if to_close:
                from app.execution.order_manager import close_position
                for p_close in to_close:
                    close_position(p_close['id'], reason=f"reversal_swing_{direction.lower()}")
        except Exception as rev_e:
            log_warning('SWING', f"Error reversión: {rev_e}")

        # 4. Apertura
        try:
            from app.core.position_sizing import calculate_position_size
            sizing = calculate_position_size(
                symbol=symbol, entry_price=execution_price, 
                sl_price=float(order.get('sl_price') or 0),
                market_type=BOT_STATE.config_cache.get('market_type', 'crypto_futures'),
                trade_number=1, regime='swing', supabase=sb
            )
            qty = sizing['quantity'] if sizing else 0
            if qty <= 0: return

            sb.table('pending_orders').update({'status': 'triggered', 'triggered_at': datetime.now(timezone.utc).isoformat()}).eq('id', order['id']).execute()
            
            # ═══════════════════════════════════════════════════════════
            # ATOMIC LIMIT CHECK — LAST LINE OF DEFENSE BEFORE INSERT
            # Re-query DB right before INSERT to catch any concurrent opens
            # ═══════════════════════════════════════════════════════════
            final_variants = crypto_symbol_match_variants(symbol)
            final_count_res = sb.table('positions').select('id', count='exact').in_('symbol', final_variants).eq('status', 'open').limit(0).execute()
            final_count = final_count_res.count if final_count_res.count is not None else 999
            if final_count >= max_symbol:
                log_warning('SWING', f"🚫 ATOMIC BLOCK: {symbol} has {final_count} open (max {max_symbol}). Swing INSERT rejected.")
                return
            # ═══════════════════════════════════════════════════════════

            pos_data = {
                'symbol': symbol, 'side': direction.upper(), 'entry_price': execution_price,
                'avg_entry_price': execution_price, 'stop_loss': float(order.get('sl_price') or 0),
                'take_profit': float(order.get('tp2_price') or 0), 'status': 'open', 'size': qty,
                'current_price': execution_price, 'opened_at': datetime.now(timezone.utc).isoformat(),
                'mode': 'paper', 'rule_code': order.get('rule_code', 'SWING')
            }
            res = sb.table('positions').insert(pos_data).execute()
            if res.data:
                p = res.data[0]
                BOT_STATE.positions[p.get('id', symbol)] = p
                log_info('SWING', f"🚀 POSICIÓN ABIERTA: {symbol} {direction.upper()} (ID: {p.get('id')})")
        except Exception as e:
            log_error('SWING', f"Error abriendo posición swing: {e}")

async def execute_limit_order_real(order, execution_price, binance_client, sb):
    log_info('SWING', f"{order['symbol']}: Real mode execution not implemented here.")
