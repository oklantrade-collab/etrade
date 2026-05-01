import pandas as pd
from datetime import datetime, timezone, timedelta
from app.core.logger import log_info, log_error, log_warning
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

async def process_swing_orders_15m(symbol: str, df_15m: pd.DataFrame, df_4h: pd.DataFrame, snap: dict, provider, sb) -> None:
    """Ciclo de gestión de órdenes Swing cada 15m"""
    
    # --- VALIDACIÓN DE LÍMITE DE POSICIONES POR SÍMBOLO ---
    # Límite configurable en Settings (por defecto 3).
    max_per_symbol = int(BOT_STATE.config_cache.get("max_positions_per_symbol", 3))

    try:
        # Contar posiciones abiertas en DB para este símbolo
        open_res = sb.table('positions').select('id', count='exact').eq('symbol', symbol).eq('status', 'open').execute()
        num_open = open_res.count or 0
        
        # Contar órdenes pendientes en DB para este símbolo
        pend_res = sb.table('pending_orders').select('id', count='exact').eq('symbol', symbol).eq('status', 'pending').execute()
        num_pending = pend_res.count or 0
        
        total_active = num_open + num_pending
        
        if total_active >= max_per_symbol:
            # Si el límite ya se alcanzó, pero TENEMOS órdenes pendientes
            # queremos procesarlas (porque process_swing_orders se encarga de RECALCULARLAS).
            # Solo abortamos si ya hay N posiciones abiertas y CERO órdenes pendientes por recalcular.
            if num_pending == 0:
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
        return # Solo Smart Limit en 15m para este módulo

    # --- PROACTIVE LIMIT CHECK (Correction #10) ---
    try:
        max_per_symbol = int(BOT_STATE.config_cache.get("max_positions_per_symbol", 4))
        # Use memory store if synced, or query DB directly for absolute safety
        from app.core.crypto_symbols import crypto_symbol_match_variants
        variants = crypto_symbol_match_variants(symbol)
        
        res_open = sb.table('positions').select('id', count='exact').in_('symbol', variants).eq('status', 'open').execute()
        current_count = res_open.count or 0
        
        if current_count >= max_per_symbol:
            log_info('SWING_LIMIT', f"{symbol}: Proactive block. {current_count} positions already open (max {max_per_symbol}).")
            # Also cancel any existing pending orders for this symbol to avoid execution
            await cancel_swing_orders(symbol, timeframe='15m', reason='limit_reached_proactive', sb=sb)
            return
    except Exception as e:
        log_error('SWING_LIMIT', f"Error in proactive limit check for {symbol}: {e}")

    for direction in ['long', 'short']:
        # ── 1. Clasificar movimiento ──────────
        movement = classify_movement(
            df    = df,
            lookback = 20,
        )

        movement_type = movement['movement_type']
        signal_bias   = movement['signal_bias']

        # ── 2. Verificar sesgo de movimiento ──
        if direction == 'long' and \
           movement_type == 'descending' and \
           movement['confidence'] > 0.80:
            log_info('SMART_LIMIT',
                f'{symbol}: LONG bloqueado — '
                f'movimiento descendente fuerte'
            )
            continue

        if direction == 'short' and \
           movement_type == 'ascending' and \
           movement['confidence'] > 0.80:
            log_info('SMART_LIMIT',
                f'{symbol}: SHORT bloqueado — '
                f'movimiento ascendente fuerte'
            )
            continue

        # ── 3. Calcular precio LIMIT óptimo ───
        limit_result = calculate_smart_limit_price(
            df            = df,
            direction     = direction,
            movement_type = movement_type,
            lookback      = 50,
            margin_pct    = 0.0015,
        )

        if not limit_result or \
           not limit_result.get('limit_price'):
            continue

        if limit_result['signal_quality'] == 'low':
            log_info('SMART_LIMIT',
                f'{symbol}/{direction}: Calidad baja — '
                f'no se coloca orden'
            )
            continue

        # ── 4. Cancelar orden anterior ────────
        await cancel_swing_order(
            symbol    = symbol,
            direction = direction,
            reason    = 'smart_limit_recalculated',
            sb        = sb
        )

        # ── 5. Calcular SL y TP ───────────────
        entry  = float(limit_result['limit_price'])
        basis  = float(snap.get('basis', 0))
        
        if direction == 'long':
            sl_price = entry * (1 - 0.005)  # 0.5% SL
            tp1_price = basis                # TP1 = BASIS
            tp2_price = float(snap.get('upper_3', basis * 1.03)) # TP2 = Upper 3
        else:
            sl_price = entry * (1 + 0.005)
            tp1_price = basis
            tp2_price = float(snap.get('lower_3', basis * 0.97))

        # ── 6. TTL según calidad y distancia ──
        ttl_hours = 2 if \
            limit_result['distance_pct'] < 1.5 \
            else 4

        # ── 7. Crear orden LIMIT en pending ───
        await create_smart_limit_order(
            symbol        = symbol,
            direction     = direction,
            limit_price   = entry,
            sl_price      = sl_price,
            tp1_price     = tp1_price,
            tp2_price     = tp2_price,
            band_target   = limit_result['band_target'],
            sizing_pct    = limit_result['sizing_pct'],
            movement_type = movement_type,
            signal_quality= limit_result['signal_quality'],
            fib_zone_entry= limit_result['fib_zone_entry'],
            ttl_hours     = ttl_hours,
            supabase      = sb
        )

        log_info('SMART_LIMIT',
            f'{symbol}/{direction}: '
            f'LIMIT ${entry:.4f} en '
            f'{limit_result["band_target"]} '
            f'(mov: {movement_type}, '
            f'calidad: {limit_result["signal_quality"]}, '
            f'sizing: {limit_result["sizing_pct"]*100:.0f}%)'
        )

        # ── 8. Alerta Telegram ────────────────
        await send_telegram_message(
            f'📍 SMART LIMIT [{symbol}]\n'
            f'Dir: {direction.upper()}\n'
            f'Movimiento: {movement_type}\n'
            f'Banda objetivo: '
            f'{limit_result["band_target"]}\n'
            f'Precio LIMIT: ${entry:.4f}\n'
            f'Distancia actual: '
            f'{limit_result["distance_pct"]:.2f}%\n'
            f'Calidad: {limit_result["signal_quality"]}\n'
            f'Sizing: {limit_result["sizing_pct"]*100:.0f}%\n'
            f'TTL: {ttl_hours}h\n'
            f'Razón: {limit_result["rationale"]}'
        )

def calculate_swing_levels(df: pd.DataFrame, direction: str, band: dict) -> dict:
    band_value = band['band_value']
    band_level = band['band_level']
    
    if direction == 'long':
        sl_level = band_level + 1
        tp1_level = band_level - 1
        sl_key = f'lower_{sl_level}'
        tp1_key = f'lower_{tp1_level}' if tp1_level >= 1 else 'basis'
        sl_price = float(df[sl_key].iloc[-1] if sl_key in df.columns else band_value * 0.985)
        tp1_price = float(df[tp1_key].iloc[-1] if tp1_key in df.columns else df['basis'].iloc[-1])
    else:
        sl_level = band_level + 1
        tp1_level = band_level - 1
        sl_key = f'upper_{sl_level}'
        tp1_key = f'upper_{tp1_level}' if tp1_level >= 1 else 'basis'
        sl_price = float(df[sl_key].iloc[-1] if sl_key in df.columns else band_value * 1.015)
        tp1_price = float(df[tp1_key].iloc[-1] if tp1_key in df.columns else df['basis'].iloc[-1])

    tp2_price = float(df['basis'].iloc[-1])
    
    # ── VALIDACIÓN DE COHERENCIA SL vs ENTRY (Swing Estándar) ──
    # Para LONG: SL DEBE estar DEBAJO del band_value (entry)
    # Para SHORT: SL DEBE estar ARRIBA del band_value (entry)
    if direction == 'long' and sl_price >= band_value:
        sl_price = band_value * 0.985  # Forzar SL 1.5% debajo
    elif direction == 'short' and sl_price <= band_value:
        sl_price = band_value * 1.015  # Forzar SL 1.5% arriba

    return {
        'limit_price': float(band_value),
        'sl_price': float(sl_price),
        'tp1_price': float(tp1_price),
        'tp2_price': float(tp2_price)
    }

async def cancel_swing_orders(symbol: str, timeframe: str = None, reason: str = 'recalculated', sb = None, direction: str = None, trade_type: str = None) -> None:
    data = {
        'status': 'cancelled',
        'cancelled_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    
    query = sb.table('pending_orders').update(data).eq('symbol', symbol).eq('status', 'pending')
    
    if timeframe:
        query = query.eq('timeframe', timeframe)
    if direction:
        query = query.eq('direction', direction)
    if trade_type:
        query = query.eq('trade_type', trade_type)
    
    res = query.execute()

async def cancel_swing_order(symbol: str, direction: str, reason: str, sb):
    """Alias/Helper para cancelar órdenes específicas"""
    await cancel_swing_orders(symbol=symbol, direction=direction, reason=reason, sb=sb)

async def create_smart_limit_order(
    symbol, direction, limit_price, sl_price, tp1_price, tp2_price, 
    band_target, sizing_pct, movement_type, signal_quality, 
    fib_zone_entry, ttl_hours, supabase
):
    new_order = {
        'symbol': symbol,
        'direction': direction,
        'order_type': 'limit',
        'trade_type': 'smart_limit',
        'rule_code': 'SMART' if direction == 'long' else 'SMART_S',
        'limit_price': limit_price,
        'sl_price': sl_price,
        'tp1_price': tp1_price,
        'tp2_price': tp2_price,
        'band_name': band_target,
        'status': 'pending',
        'mode': 'paper' if BOT_STATE.config_cache.get("paper_trading", True) else 'real',
        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat(),
        'sizing_pct': sizing_pct,
        'timeframe': '15m',
        # Nuevos campos
        'movement_type': movement_type,
        'signal_quality': signal_quality,
        'fib_zone_entry': fib_zone_entry
    }
    supabase.table('pending_orders').insert(new_order).execute()


async def create_swing_order(symbol: str, direction: str, timeframe: str, band: dict, levels: dict, rule_code: str, basis_slope: float, sizing_pct: float, expire_hours: int, sb, trade_type: str = 'swing') -> None:
    new_order = {
        'symbol': symbol,
        'direction': direction,
        'order_type': 'limit',
        'trade_type': trade_type,
        'rule_code': rule_code,
        'limit_price': levels['limit_price'],
        'sl_price': levels['sl_price'],
        'tp1_price': levels['tp1_price'],
        'tp2_price': levels['tp2_price'],
        'band_name': band['band_name'],
        'basis_slope': basis_slope,
        'status': 'pending',
        'mode': 'paper' if BOT_STATE.config_cache.get("paper_trading", True) else 'real',
        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=expire_hours)).isoformat(),
        'version': 1,
        'sizing_pct': sizing_pct,
        'timeframe': timeframe
    }

    sb.table('pending_orders').insert(new_order).execute()
    log_info('SWING', f'{symbol}: orden LIMIT creada {direction.upper()} @ ${levels["limit_price"]:,.4f} banda {band["band_name"]} (TF: {timeframe}) - {rule_code}')

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
                log_info('SWING', f'{symbol}: orden expirada @ ${limit_price:,.4f}')
                continue

        price_hit = (direction == 'long' and current_price <= limit_price) or (direction == 'short' and current_price >= limit_price)
        if not price_hit: continue

        log_info('SWING', f'{symbol}: LIMIT EJECUTADO {direction.upper()} @ ${current_price:,.4f} (limit: ${limit_price:,.4f})')

        if is_paper:
            await execute_limit_order_paper(order=order, execution_price=current_price, sb=sb)
        else:
            await execute_limit_order_real(order=order, execution_price=current_price, binance_client=provider, sb=sb)

async def execute_limit_order_paper(order: dict, execution_price: float, sb) -> None:
    symbol = order['symbol']
    direction = order['direction']

    # --- VALIDACIÓN DE LÍMITES (GLOBAL Y SÍMBOLO) CON LOCK ---
    async with BOT_STATE.order_lock:
        try:
            # 1. Límite Global
            max_global = int(BOT_STATE.config_cache.get('max_open_trades', 3))
            pos_res = sb.table('positions').select('id').eq('status', 'open').execute()
            current_global = len(pos_res.data) if pos_res.data else 0
            
            if current_global >= max_global:
                log_warning('SWING', f"GLOBAL_LIMIT: {symbol} bloqueado. Límite global de {max_global} alcanzado ({current_global}).")
                return

            # 2. Límite por Símbolo
            from app.core.crypto_symbols import crypto_symbol_match_variants
            max_symbol = int(BOT_STATE.config_cache.get('max_positions_per_symbol', 3))
            variants = crypto_symbol_match_variants(symbol)
            sym_pos_res = sb.table('positions').select('id').in_('symbol', variants).eq('status', 'open').execute()
            current_sym = len(sym_pos_res.data) if sym_pos_res.data else 0
            
            if current_sym >= max_symbol:
                log_warning('SWING', f"SYMBOL_LIMIT: {symbol} bloqueado. Límite por símbolo de {max_symbol} alcanzado ({current_sym}).")
                await cancel_swing_orders(symbol, timeframe=order.get('timeframe',''), reason='limit_reached', sb=sb)
                return
        except Exception as limit_e:
            log_error('SWING', f"Error validando límites en ejecución: {limit_e}")
            return

        # ── REVERSIÓN FORZADA (Hedge no permitido) ──
        # Si ejecutamos un Smart Limit y hay posiciones opuestas, cerrarlas primero.
        try:
            from app.core.crypto_symbols import crypto_symbol_match_variants
            opposite_side = 'SHORT' if direction.lower() == 'long' else 'LONG'
            opp_res = sb.table('positions').select('*').in_('symbol', crypto_symbol_match_variants(symbol)).eq('status', 'open').execute()
            
            to_close = []
            for p in (opp_res.data or []):
                p_side = (p.get('side') or '').upper()
                if opposite_side == 'SHORT' and p_side in ('SHORT', 'SELL'):
                    to_close.append(p)
                elif opposite_side == 'LONG' and p_side in ('LONG', 'BUY'):
                    to_close.append(p)
            
            if to_close:
                log_info('SWING', f"🔄 REVERSIÓN: Cerrando {len(to_close)} posiciones opuestas en {symbol} antes de ejecutar {direction.upper()}")
                from app.execution.order_manager import close_position
                for p_close in to_close:
                    close_position(p_close['id'], reason=f"reversal_smart_{direction.lower()}")
        except Exception as rev_e:
            log_warning('SWING', f"Error en reversión automática: {rev_e}")

        # Continuar con el proceso original si pasó los límites
        from app.core.memory_store import MARKET_SNAPSHOT_CACHE
        snap = MARKET_SNAPSHOT_CACHE.get(symbol, {})
        regime = snap.get('regime_category', 'bajo_riesgo')
        params = get_active_params(regime=regime, supabase_client=sb)
        market_type = BOT_STATE.config_cache.get('market_type', 'crypto_futures')
        sizing = calculate_position_size(
            symbol=symbol,
            entry_price=execution_price,
            sl_price=float(order.get('sl_price') or 0),
            market_type=market_type,
            trade_number=1,
            regime=regime,
            supabase=sb
        )
        qty = sizing['quantity'] if sizing else 0
        if qty <= 0:
            log_error('SWING', f"Could not calculate quantity for {symbol}")
            return

        sb.table('pending_orders').update({
            'status': 'triggered',
            'triggered_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', order['id']).execute()
        
        sl_value = float(order.get('sl_price') or 0)
        
        # ── VALIDACIÓN FINAL DE COHERENCIA SL vs PRECIO DE EJECUCIÓN ──
        # Previene que un SL quede en el lado incorrecto del entry
        if direction == 'long' and sl_value >= execution_price and sl_value > 0:
            sl_value = execution_price * 0.995  # Forzar SL 0.5% debajo del entry
            log_warning('SWING', f"{symbol}: SL corregido en ejecución LONG. SL={sl_value:.6f} < Entry={execution_price:.6f}")
        elif direction == 'short' and sl_value <= execution_price and sl_value > 0:
            sl_value = execution_price * 1.005  # Forzar SL 0.5% arriba del entry
            log_warning('SWING', f"{symbol}: SL corregido en ejecución SHORT. SL={sl_value:.6f} > Entry={execution_price:.6f}")

        pos_data = {
            'symbol': symbol,
            'side': direction,
            'entry_price': execution_price,
            'avg_entry_price': execution_price,
            'stop_loss': sl_value,
            'take_profit': float(order.get('tp2_price') or 0),
            'sl_price': sl_value,
            'tp_partial_price': float(order.get('tp1_price') or 0),
            'tp_full_price': float(order.get('tp2_price') or 0),
            'rule_code': order.get('rule_code', 'Dd11'),
            'rule_entry': order.get('rule_code', 'Dd11'),
            'status': 'open',
            'is_open': True,
            'size': qty,
            'current_price': execution_price,
            'opened_at': datetime.now(timezone.utc).isoformat(),
            'mode': 'paper'
        }

        # Dashboard log (orders table)
        try:
            sb.table('orders').insert({
                'symbol': symbol,
                'side': 'BUY' if direction == 'long' else 'SELL',
                'order_type': 'LIMIT',
                'quantity': qty,
                'limit_price': float(order.get('limit_price') or 0),
                'entry_price': execution_price,
                'stop_loss_price': sl_value,
                'take_profit_price': float(order.get('tp2_price') or 0),
                'status': 'open',
                'is_paper': True,
                'rule_code': order.get('rule_code', 'Dd11')
            }).execute()
        except Exception as e:
            log_warning('SWING', f"Failed to log swing order to orders table: {e}")

        res = sb.table('positions').upsert(pos_data).execute()
        if res.data:
            # Key by pos_id to support multiple positions per symbol
            new_pos = res.data[0]
            BOT_STATE.positions[new_pos.get('id', symbol)] = new_pos

        if asyncio.iscoroutinefunction(send_telegram_message):
            await send_telegram_message(
                f"⚡ LIMIT EJECUTADO — SWING [{symbol}]\n"
                f"Regla: {order.get('rule_code', '')}\n"
                f"Dirección: {direction.upper()}\n"
                f"Precio ejecución: ${execution_price:,.4f}\n"
                f"Precio limit:     ${float(order.get('limit_price', 0)):,.4f}\n"
                f"Banda: {order.get('band_name', '')}\n"
                f"SL:  ${float(order.get('sl_price', 0)):,.4f}\n"
                f"TP1: ${float(order.get('tp1_price', 0)):,.4f}\n"
                f"TP2: ${float(order.get('tp2_price', 0)):,.4f}"
            )

async def execute_limit_order_real(order: dict, execution_price: float, binance_client, sb) -> None:
    log_info('SWING', f"{order['symbol']}: Real mode execution pending validation...")
