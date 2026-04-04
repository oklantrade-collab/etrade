import pandas as pd
from datetime import datetime, timezone, timedelta
from app.core.logger import log_info, log_error, log_warning
from app.analysis.swing_detector import detect_basis_horizontal, find_current_band_zone, SWING_CONFIG, calculate_fall_maturity
from app.core.position_sizing import can_open_short, calculate_position_size
from app.core.parameter_guard import get_active_params
from app.workers.performance_monitor import send_telegram_message
from app.core.memory_store import BOT_STATE
import asyncio

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

async def process_swing_orders(symbol: str, timeframe: str, df: pd.DataFrame, snap: dict, sb) -> None:
    market_type = BOT_STATE.config_cache.get('market_type', 'crypto_futures')
    cfg = SWING_CONFIG.get(timeframe)
    if not cfg: return

    # 1. Detectar Régimen Lateral (Rango Plano) - Umbral 0.5% (Estrategia Dd61/Dd51)
    horizontal = detect_basis_horizontal(df, lookback=10, slope_threshold=0.5)
    is_flat = horizontal['is_flat']
    log_info('SWING', f"{symbol}/{timeframe}: is_flat={is_flat} (slope={horizontal['slope_pct']:.4f}%)")

    # ── Leer estructura 4h del snapshot ──
    allow_long_4h  = bool(snap.get('allow_long_4h',  True))
    allow_short_4h = bool(snap.get('allow_short_4h', True))
    reverse_4h     = bool(snap.get('reverse_signal_4h', False))

    for direction in ['long', 'short']:
        if direction == 'short' and not can_open_short(market_type):
            continue

        # ── 2. Selección de Regla y Niveles ──
        if is_flat:
            # --- ESTRATEGIA TRAP (Dd61 / Dd51) ---
            rule_code = 'Dd61' if direction == 'long' else 'Dd51'

            # ── NUEVO: FILTRO DE COOLDOWN POST-SL (15 MINUTOS) ──
            try:
                limit_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
                recent_sl = sb.table('paper_trades').select('id')\
                    .eq('symbol', symbol)\
                    .eq('rule_code', rule_code)\
                    .eq('close_reason', 'sl')\
                    .gte('closed_at', limit_time)\
                    .execute()
                    
                if recent_sl.data:
                    log_info('SWING', f"{symbol}: Cooldown de 15m activo para {rule_code} (SL reciente).")
                    continue
            except Exception as cooldown_e:
                log_error('SWING', f"Error en validación de cooldown: {cooldown_e}")
            
            # FILTRO BASIS: Solo pesca si ya estamos en la mitad correcta del canal
            basis_val = float(df['basis'].iloc[-1])
            current_p = float(df['close'].iloc[-1])
            
            if direction == 'long' and current_p >= basis_val:
                continue # No compra si estamos arriba del basis
            if direction == 'short' and current_p <= basis_val:
                continue # No vende si estamos abajo del basis

            band = find_current_band_zone(df, direction)
            
            # Si no hay toque en zona extrema (L6/U6), no operamos Trap reactivamente
            if not band:
                continue
            
            # --- VALIDACIÓN DINÁMICA POR SCORE (Requirement: Sync with UI Rules) ---
            # Si la regla Dd51/Dd61 existe en el motor, validamos el score (ej: 0.75)
            from app.strategy.strategy_engine import StrategyEngine
            engine = StrategyEngine.get_instance(sb)
            if engine and engine.rules:
                # El usuario puede usar Dd51 o Dd51_15m
                possible_codes = [rule_code, f"{rule_code}_{timeframe}"]
                match_rule = next((engine.rules.get(c) for c in possible_codes if c in engine.rules), None)
                
                if match_rule:
                    from app.core.memory_store import get_memory_df
                    df_15m_ctx = get_memory_df(symbol, "15m") if timeframe != "15m" else df
                    df_4h_ctx = get_memory_df(symbol, "4h") if timeframe != "4h" else df
                    context = engine.build_context(snap=snap, df_15m=df_15m_ctx, df_4h=df_4h_ctx)
                    
                    eval_res = engine.evaluate_rule(match_rule, context)
                    if not eval_res['triggered']:
                        log_info('SWING', f"{symbol}/{timeframe}: {rule_code} rechazada por SCORE ({eval_res['score']:.2f} < {eval_res['min_score']})")
                        continue
                    else:
                        log_info('SWING', f"{symbol}/{timeframe}: {rule_code} aprobada por SCORE ({eval_res['score']:.2f} >= {eval_res['min_score']})")

            band_val = band['band_value']

            # ── NUEVO: BUFFER DE SL DINÁMICO (PATRONES DE VOLATILIDAD) ──
            current_adx = float(snap.get('adx', 25))
            if current_adx < 20: 
                sl_buffer = 0.003 # 0.3% Estable
                vol_label = "ESTABLE"
            elif current_adx < 35:
                sl_buffer = 0.005 # 0.5% Neutro
                vol_label = "NEUTRO"
            else:
                sl_buffer = 0.007 # 0.7% VOLATIL
                vol_label = "VOLATIL"

            # Margen sugerido: 0.05% de buffer hacia el mercado (hacia Basis)
            fill_margin = 0.0005
            limit_p = band_val * (1 + fill_margin) if direction == 'long' else band_val * (1 - fill_margin)
            
            # SL dinámico según patrón de volatilidad
            sl_p = band_val * (1 - sl_buffer) if direction == 'long' else band_val * (1 + sl_buffer)
            tp_p = float(df['basis'].iloc[-1])
            
            levels = {
                'limit_price': limit_p,
                'sl_price': sl_p,
                'tp1_price': tp_p,
                'tp2_price': tp_p
            }
            
            band_maturity = {
                'band_name': band['band_name'],
                'band_level': band['band_level'],
                'band_value': band_val,
                'is_mature': True  # Forzamos madurez proactiva en modo Trap
            }
            log_info('SWING', f"{symbol}/{timeframe}: {rule_code} ({vol_label}) activa. SL: {sl_buffer*100}% Caza en ${limit_p:,.4f}")
            
            # TTL 2h y Timeframe original (15m/4h) pero con trade_type='trap'
            await cancel_swing_orders(symbol, direction=direction, trade_type='trap', timeframe=timeframe, reason='recalculated', sb=sb)
            await create_swing_order(
                symbol=symbol, direction=direction, timeframe=timeframe,
                band=band_maturity, levels=levels, rule_code=rule_code,
                basis_slope=horizontal['slope_pct'], sizing_pct=float(cfg['sizing_pct']),
                expire_hours=2, sb=sb, trade_type='trap'
            )
            continue # Procesa la siguiente dirección

        else:
            # --- ESTRATEGIA SWING ESTÁNDAR (Dd21 / Dd11) ---
            rule_code = 'Dd21' if direction == 'long' else 'Dd11'

            if direction == 'long':
                swing_authorized = allow_long_4h or (reverse_4h and allow_long_4h)
                if not swing_authorized:
                    band = find_current_band_zone(df, 'long')
                    if band and band.get('band_level', 0) >= 6:
                        swing_authorized = True
                    else: continue
            elif direction == 'short':
                swing_authorized = allow_short_4h or (reverse_4h and allow_short_4h)
                if not swing_authorized:
                    band = find_current_band_zone(df, 'short')
                    if band and band.get('band_level', 0) >= 6:
                        swing_authorized = True
                    else: continue

            band_maturity = calculate_fall_maturity(
                df=df, direction=direction, lookback=cfg['lookback'],
                min_bands=cfg['min_bands'], min_basis_dist=cfg['min_basis_dist']
            )

            if not band_maturity.get('is_mature'):
                await cancel_swing_orders(symbol, timeframe, f"no_maturity_{direction}", sb, direction)
                log_info('SWING', f"{symbol}/{timeframe}: {direction.upper()} not mature: {band_maturity.get('reason')}")
                continue
                
            log_info('SWING', f"{symbol}/{timeframe}: {direction.upper()} mature. Bands: {band_maturity.get('bands_perforated')}")
            levels = calculate_swing_levels(df, direction, band_maturity)

            # ── 3. Ejecución de la Orden (Swing Estándar) ──
            await cancel_swing_orders(symbol, direction=direction, timeframe=timeframe, reason='recalculated', sb=sb)
            await create_swing_order(
                symbol=symbol, direction=direction, timeframe=timeframe,
                band=band_maturity, levels=levels, rule_code=rule_code,
                basis_slope=horizontal['slope_pct'], sizing_pct=float(cfg['sizing_pct']),
                expire_hours=int(cfg['ttl_hours']), sb=sb
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

    # --- VALIDACIÓN DE LÍMITES (GLOBAL Y SÍMBOLO) ---
    try:
        # 1. Límite Global
        max_global = int(BOT_STATE.config_cache.get('max_open_trades', 3))
        pos_res = sb.table('positions').select('id').eq('status', 'open').execute()
        current_global = len(pos_res.data) if pos_res.data else 0
        
        if current_global >= max_global:
            log_warning('SWING', f"GLOBAL_LIMIT: {symbol} bloqueado. Límite global de {max_global} alcanzado ({current_global}).")
            return

        # 2. Límite por Símbolo
        max_symbol = int(BOT_STATE.config_cache.get('max_positions_per_symbol', 3))
        sym_pos_res = sb.table('positions').select('id').eq('symbol', symbol).eq('status', 'open').execute()
        current_sym = len(sym_pos_res.data) if sym_pos_res.data else 0
        
        if current_sym >= max_symbol:
            log_warning('SWING', f"SYMBOL_LIMIT: {symbol} bloqueado. Límite por símbolo de {max_symbol} alcanzado ({current_sym}).")
            # Si alcanzamos el límite, deberíamos cancelar cualquier otra órdenes pendientes de este símbolo
            # para evitar que se ejecuten después y sigan sobrepasando el límite.
            await cancel_swing_orders(symbol, timeframe=order.get('timeframe',''), reason='limit_reached', sb=sb)
            return

    except Exception as limit_e:
        log_error('SWING', f"Error validando límites en ejecución: {limit_e}")

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
    
    pos_data = {
        'symbol': symbol,
        'side': direction,
        'entry_price': execution_price,
        'avg_entry_price': execution_price,
        'stop_loss': float(order.get('sl_price') or 0),
        'take_profit': float(order.get('tp2_price') or 0),
        'sl_price': float(order.get('sl_price') or 0),
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
            'stop_loss_price': float(order.get('sl_price') or 0),
            'take_profit_price': float(order.get('tp2_price') or 0),
            'status': 'open',
            'is_paper': True,
            'rule_code': order.get('rule_code', 'Dd11')
        }).execute()
    except Exception as e:
        log_warning('SWING', f"Failed to log swing order to orders table: {e}")

    res = sb.table('positions').upsert(pos_data).execute()
    if res.data:
        BOT_STATE.positions[symbol] = res.data[0]

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
