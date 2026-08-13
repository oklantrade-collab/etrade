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

async def process_swing_ema_strategy(symbol: str, df_15m: pd.DataFrame, snap: dict, sb) -> None:
    """
    Estrategia SwingEma (ApexEma): LONG/SHORT basada en EMA3/9/20/50/200, 
    Sizing 40/60, Distancia Mínima 0.4%, Pendiente EMA200, y traspaso a EREP.
    """
    if df_15m is None or len(df_15m) < 200:
        return
        
    # 1. Calcular EMAs
    df = df_15m.copy()
    df['ema3'] = df['close'].ewm(span=3, adjust=False).mean()
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # Obtener valores actuales (vela cerrada más reciente)
    last_row = df.iloc[-1]
    ema3 = float(last_row['ema3'])
    ema9 = float(last_row['ema9'])
    ema20 = float(last_row['ema20'])
    ema50 = float(last_row['ema50'])
    ema200 = float(last_row['ema200'])
    
    # Obtener valores de hace 3 velas para pendiente de EMA200
    ema200_3 = float(df.iloc[-4]['ema200']) if len(df) >= 4 else ema200
    
    current_price = float(last_row['close'])
    
    # 2. Verificar posiciones abiertas de esta estrategia
    is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF'))
    table_name = 'forex_positions' if is_forex else 'positions'
    variants = crypto_symbol_match_variants(symbol)
    try:
        open_res = sb.table(table_name).select('*').in_('symbol', variants).eq('status', 'open').in_('rule_code', ['AaApexEma', 'BbApexEma']).execute()
        open_positions = open_res.data or []
    except Exception as e:
        log_error('APEX_EMA', f"Error consultando posiciones abiertas para {symbol}: {e}")
        open_positions = []
        
    # 3. Transición Proactiva a EREP en caso de Reversión
    if open_positions:
        for pos in open_positions:
            side = (pos.get('side') or '').upper()
            rule = pos.get('rule_code')
            
            reversal = False
            if side == 'LONG' and ema3 < ema9:
                reversal = True
            elif side == 'SHORT' and ema3 > ema9:
                reversal = True
                
            if reversal:
                # Traspasar a EREP Fase 2
                log_info('APEX_EMA', f"⚠️ [REVERSAL] Traspasando posición {pos['id']} ({symbol} {side}) a EREP Fase 2 de forma proactiva.")
                try:
                    if is_forex:
                        update_data = {
                            'sl_price': 0,
                            'erep_active': True,
                            'erep_phase': 2,
                            'erep_p1_price': float(pos.get('avg_entry_price') or pos.get('entry_price') or current_price),
                            'erep_market_type': 'forex_futures',
                            'erep_cycles_elapsed': 0,
                            'erep_q1': float(pos.get('lots') or 0)
                        }
                    else:
                        update_data = {
                            'sl_type': 'suspended_negative_protection',
                            'sl_price': 0,
                            'sl_dynamic_price': 0,
                            'stop_loss': 0,
                            'erep_active': True,
                            'erep_phase': 2,
                            'erep_p1_price': float(pos.get('avg_entry_price') or pos.get('entry_price') or current_price),
                            'erep_market_type': 'crypto_futures',
                            'erep_cycles_elapsed': 0,
                            'erep_q1': float(pos.get('size') or 0)
                        }

                    sb.table(table_name).update(update_data).eq('id', pos['id']).execute()
                    
                    # Actualizar memoria
                    if pos['id'] in BOT_STATE.positions:
                        memory_update = {
                            'sl_price': 0,
                            'erep_active': True,
                            'erep_phase': 2,
                            'erep_cycles_elapsed': 0
                        }
                        if not is_forex:
                            memory_update.update({
                                'sl_type': 'suspended_negative_protection',
                                'stop_loss': 0,
                                'sl_dynamic_price': 0
                            })
                        BOT_STATE.positions[pos['id']].update(memory_update)
                except Exception as erep_e:
                    log_error('APEX_EMA', f"Error traspasando posición {pos['id']} a EREP: {erep_e}")
        return  # Si ya hay posiciones abiertas o en proceso de EREP, no colocamos nuevas órdenes límite

    # 4. Verificar órdenes pendientes existentes
    try:
        pend_res = sb.table('pending_orders').select('*').in_('symbol', variants).eq('status', 'pending').in_('rule_code', ['AaApexEma', 'BbApexEma']).execute()
        pending_orders = pend_res.data or []
    except Exception as e:
        log_error('APEX_EMA', f"Error consultando órdenes pendientes para {symbol}: {e}")
        pending_orders = []

    # 5. Condición de Cancelación de Pendientes (Reversión de tendencia antes de ejecutar)
    if pending_orders:
        cancel_long = (ema3 < ema9)
        cancel_short = (ema3 > ema9)
        
        has_cancelled = False
        for po in pending_orders:
            rule = po.get('rule_code')
            if (rule == 'AaApexEma' and cancel_long) or (rule == 'BbApexEma' and cancel_short):
                log_info('APEX_EMA', f"🧹 [CANCEL PENDING] Cancelando orden pendiente {po['id']} de {symbol} ({rule}) por reversión rápida.")
                try:
                    sb.table('pending_orders').update({
                        'status': 'cancelled',
                        'cancelled_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat(),
                        'rejection_reason': 'ema_reversal'
                    }).eq('id', po['id']).execute()
                    has_cancelled = True
                except Exception as cancel_e:
                    log_error('APEX_EMA', f"Error cancelando orden pendiente {po['id']}: {cancel_e}")
        if has_cancelled:
            return

    # Si ya hay órdenes pendientes colocadas que no se cancelaron, no hacemos nada más
    if pending_orders:
        return

    # 6. Evaluar Gatillo de Entrada con Filtro de Tendencia Macro 1H (EMA3 vs EMA9 en velas cerradas)
    from app.core.memory_store import get_memory_df
    df_1h = get_memory_df(symbol, "1h")
    
    macro_long_ok = True
    macro_short_ok = True
    
    if df_1h is not None and len(df_1h) >= 10:
        ema3_1h = df_1h['close'].ewm(span=3, adjust=False).mean()
        ema9_1h = df_1h['close'].ewm(span=9, adjust=False).mean()
        # Evaluamos iloc[-2] (vela de 1H completamente cerrada) para evitar repintado en tiempo real
        last_ema3_1h = float(ema3_1h.iloc[-2])
        last_ema9_1h = float(ema9_1h.iloc[-2])
        
        macro_long_ok = (last_ema3_1h > last_ema9_1h)
        macro_short_ok = (last_ema3_1h < last_ema9_1h)

    # Validar que la Banda Superior de Bollinger en 15m esté ascendente (Upper Slope 15m > 0)
    upper_col = 'upper_1' if 'upper_1' in df_15m.columns else ('upper_bollinger' if 'upper_bollinger' in df_15m.columns else None)
    if upper_col and upper_col in df_15m.columns:
        bb_upper_series = df_15m[upper_col]
    else:
        bb_basis = df_15m['close'].rolling(20).mean()
        bb_std = df_15m['close'].rolling(20).std()
        bb_upper_series = bb_basis + (2.0 * bb_std)

    upper_slope_15m = float(bb_upper_series.iloc[-1] - bb_upper_series.iloc[-2]) if len(bb_upper_series) >= 2 else 1.0

    trigger_long = (ema3 > ema9) and (ema9 > ema20) and (ema50 > ema200) and (ema200 > ema200_3) and (upper_slope_15m > 0) and macro_long_ok
    trigger_short = (ema3 < ema9) and (ema9 < ema20) and (ema50 < ema200) and (ema200 < ema200_3) and macro_short_ok
    
    if not trigger_long and not trigger_short:
        return

    # 6b. Confirmación SIPV (acción del precio): exigir vela coherente con la dirección
    # Para doji, exigimos que el cierre esté a favor de la tendencia o usamos patrones más fuertes.
    close_price_candle = float(last_row.get('close', 0))
    open_price_candle = float(last_row.get('open', 0))
    high_price_candle = float(last_row.get('high', 0))
    low_price_candle = float(last_row.get('low', 0))
    
    is_doji = last_row.get('is_doji', False)
    doji_long = is_doji and (close_price_candle >= low_price_candle + (high_price_candle - low_price_candle) * 0.5)
    doji_short = is_doji and (close_price_candle <= high_price_candle - (high_price_candle - low_price_candle) * 0.5)

    sipv_long = bool(
        last_row.get('is_dragonfly', False) or
        last_row.get('is_bullish_engulfing', False) or
        last_row.get('low_higher_than_prev', False) or
        last_row.get('is_hammer', False) or
        doji_long or
        (close_price_candle > open_price_candle)  # Vela verde
    )
    sipv_short = bool(
        last_row.get('is_gravestone', False) or
        last_row.get('is_bearish_engulfing', False) or
        last_row.get('high_lower_than_prev', False) or
        doji_short or
        (close_price_candle < open_price_candle)  # Vela roja
    )

    if trigger_long and not sipv_long:
        log_debug('APEX_EMA', f"[{symbol}] EMA Stack LONG OK pero vela no confirma (SIPV). Esperando.")
        return
    if trigger_short and not sipv_short:
        log_debug('APEX_EMA', f"[{symbol}] EMA Stack SHORT OK pero vela no confirma (SIPV). Esperando.")
        return

    direction = 'long' if trigger_long else 'short'
    rule_code = 'AaApexEma' if trigger_long else 'BbApexEma'
    
    # 7. Calcular cantidad de la posición total
    try:
        from app.core.position_sizing import calculate_position_size
        # Sizing aproximado basado en el precio actual
        sizing = calculate_position_size(
            symbol=symbol, entry_price=current_price, sl_price=current_price * (0.985 if trigger_long else 1.015),
            market_type=BOT_STATE.config_cache.get('market_type', 'crypto_futures'),
            trade_number=1, regime='swing', supabase=sb
        )
        total_qty = float(sizing['quantity'] if sizing else 0)
    except Exception as sz_e:
        log_error('APEX_EMA', f"Error calculando sizing para {symbol}: {sz_e}")
        total_qty = 0
        
    if total_qty <= 0:
        return

    # 8. Filtro de Distancia Mínima de Soporte (0.4%) y FOMO Threshold (0.08%)
    dist_pct = abs(ema9 - ema20) / ema20
    dist_to_ema9 = abs(current_price - ema9) / ema9
    
    orders_to_place = []
    
    # Si estamos muy cerca de EMA9 (FOMO), aseguramos 20% inmediato
    if dist_to_ema9 <= 0.0008:
        qty_fomo = total_qty * 0.20
        rem_qty = total_qty * 0.80
        orders_to_place.append({
            'limit_price': current_price,
            'qty': qty_fomo,
            'name': 'Order FOMO'
        })
        log_info('APEX_EMA', f"[{symbol}] FOMO detectado (dist: {dist_to_ema9:.4f}). Separando 20% a precio actual.")
    else:
        rem_qty = total_qty

    # Extraer o calcular niveles Lower_5 y Lower_6 en 5m
    import math
    
    def safe_get(row, key, default_val):
        val = row.get(key)
        if pd.isna(val) or val is None:
            return default_val
        try:
            f_val = float(val)
            if math.isnan(f_val):
                return default_val
            return f_val
        except (ValueError, TypeError):
            return default_val

    lower_5_5m = safe_get(last_row, 'lower_5', 0.0)
    lower_6_5m = safe_get(last_row, 'lower_6', 0.0)
    
    if math.isnan(lower_5_5m) or lower_5_5m <= 0:
        bb_basis = safe_get(last_row, 'basis', current_price)
        bb_std = safe_get(last_row, 'std', current_price * 0.005)
        lower_5_5m = bb_basis - (2.5 * bb_std)
        lower_6_5m = bb_basis - (3.0 * bb_std)

    if trigger_long:
        px_order1 = lower_5_5m
        px_order2 = lower_6_5m
        name_1 = 'Order 1 (Lower_5 5m)'
        name_2 = 'Order 2 (Lower_6 5m)'
    else:
        upper_5_5m = safe_get(last_row, 'upper_5', 0.0)
        upper_6_5m = safe_get(last_row, 'upper_6', 0.0)
        if math.isnan(upper_5_5m) or upper_5_5m <= 0:
            bb_basis = safe_get(last_row, 'basis', current_price)
            bb_std = safe_get(last_row, 'std', current_price * 0.005)
            upper_5_5m = bb_basis + (2.5 * bb_std)
            upper_6_5m = bb_basis + (3.0 * bb_std)
        px_order1 = upper_5_5m
        px_order2 = upper_6_5m
        name_1 = 'Order 1 (Upper_5 5m)'
        name_2 = 'Order 2 (Upper_6 5m)'

    # Colocar 2 órdenes limitadas (Sizing 40/60 del remanente en Lower_5 y Lower_6 de 5m)
    orders_to_place.append({
        'limit_price': px_order1,
        'qty': rem_qty * 0.40,
        'name': name_1
    })
    orders_to_place.append({
        'limit_price': px_order2,
        'qty': rem_qty * 0.60,
        'name': name_2
    })

    # 9. Insertar Órdenes Límite en la base de datos
    is_paper = BOT_STATE.config_cache.get("paper_trading", False) is not False
    mode_val = 'paper' if is_paper else 'real'
    ttl_hours = 4  # 4 horas de expiración estándar para Swing
    
    import math
    for op in orders_to_place:
        limit_px = round(op['limit_price'], 4)
        
        if 'BTC' in symbol.upper():
            size_val = max(0.001, round(op['qty'], 3))
        elif 'ETH' in symbol.upper():
            size_val = max(0.01, round(op['qty'], 3))
        else:
            size_val = round(op['qty'], 4)
        
        if math.isnan(limit_px) or math.isnan(size_val) or math.isinf(limit_px) or math.isinf(size_val):
            log_error('APEX_EMA', f"[{symbol}] Orden ignorada por valor NaN/Inf: limit={limit_px}, qty={size_val}")
            continue
            
        if size_val <= 0:
            log_warning('APEX_EMA', f"[{symbol}] Orden ignorada: Cantidad calculada ({size_val}) es cero o insuficiente. Verifica tu capital asignado y riesgo.")
            continue
            
        new_order = {
            'symbol': symbol,
            'direction': direction,
            'order_type': 'limit',
            'trade_type': 'swing_ema',
            'rule_code': rule_code,
            'limit_price': limit_px,
            'sl_price': 0,  # Se deja vacío inicialmente, delegación virtual
            'tp1_price': 0,
            'tp2_price': 0,
            'band_name': str(op['name'])[:20],
            'status': 'pending',
            'mode': mode_val,
            'expires_at': (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat(),
            'sizing_pct': 1.00 if len(orders_to_place) == 1 else (0.40 if 'Order 1' in op['name'] else 0.60),
            'timeframe': '15m',
            'movement_type': 'trend_ema',
            'signal_quality': 'high',
            'fib_zone_entry': 0
        }
        
        try:
            sb.table('pending_orders').insert(new_order).execute()
            log_info('APEX_EMA', f"🎯 [PLACED LIMIT] {symbol} {rule_code}: {op['name']} colocada a ${limit_px:.4f} | Cantidad: {size_val}")
            
            # Alerta Telegram (Removida por solicitud del usuario para evitar ruido)
            pass
        except Exception as ins_e:
            log_error('APEX_EMA', f"Error insertando orden límite {op['name']} en DB: {ins_e}")

async def process_swing_orders_15m(symbol: str, df_15m: pd.DataFrame, df_4h: pd.DataFrame, snap: dict, provider, sb) -> None:
    """Ciclo de gestión de órdenes Swing cada 15m"""
    
    # --- ESTRATEGIA CUSTOM APEX_EMA (SwingEma) ---
    try:
        await process_swing_ema_strategy(symbol, df_15m, snap, sb)
    except Exception as ema_err:
        log_error('APEX_EMA', f"Error en estrategia ApexEma para {symbol}: {ema_err}")
    
    # --- VALIDACIÓN DE LÍMITE DE POSICIONES POR SÍMBOLO ---
    max_per_symbol = int(BOT_STATE.config_cache.get("max_positions_per_symbol", 4))

    try:
        # Contar posiciones abiertas en DB para este símbolo (atómico)
        is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF'))
        table_name = 'forex_positions' if is_forex else 'positions'
        variants = crypto_symbol_match_variants(symbol)
        open_res = sb.table(table_name).select('id', count='exact').in_('symbol', variants).eq('status', 'open').limit(0).execute()
        num_open = open_res.count if open_res.count is not None else 999
        
        # Contar órdenes pendientes en DB para este símbolo
        pend_res = sb.table('pending_orders').select('id', count='exact').in_('symbol', variants).eq('status', 'pending').limit(0).execute()
        num_pending = pend_res.count if pend_res.count is not None else 0
        
        total_active = num_open + num_pending
        
        if total_active >= max_per_symbol:
            if num_pending == 0:
                log_debug('SWING_LIMITS', f"{symbol}: Límite alcanzado ({num_open}/{max_per_symbol}).")
                return

        # Validar límite de monedas activas simultáneas (Cant. Monedas Activas)
        all_open_res = sb.table(table_name).select('symbol').eq('status', 'open').execute()
        active_symbols_set = set(p['symbol'] for p in (all_open_res.data or []))
        
        tc_res = sb.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
        tc_data = tc_res.data if tc_res and tc_res.data else {}
        reg_params = tc_data.get('regime_params', {}) or {}
        max_active_syms = int(reg_params.get('max_active_symbols_forex' if is_forex else 'max_active_symbols_crypto', 1))

        if symbol not in active_symbols_set and len(active_symbols_set) >= max_active_syms:
            log_debug('SWING_LIMITS', f"⛔ [MONEDAS ACTIVAS] {symbol} omitido. Ya hay {len(active_symbols_set)}/{max_active_syms} activos: {list(active_symbols_set)}")
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
        is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF'))
        table_name = 'forex_positions' if is_forex else 'positions'
        variants = crypto_symbol_match_variants(symbol)
        
        res_open = sb.table(table_name).select('id', count='exact').in_('symbol', variants).eq('status', 'open').limit(0).execute()
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

        is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF'))
        max_dist = 0.4 if is_forex else 2.5

        # 2. Calcular precio LIMIT óptimo
        limit_result = calculate_smart_limit_price(
            df=df, direction=direction, movement_type=movement_type, 
            lookback=50, margin_pct=0.0015, max_distance_pct=max_dist
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
        # Telegram log removed to avoid spam, will only alert on execution

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

async def enforce_global_limit_max(supabase, mode, max_limits=5):
    # ── 1. LIMPIEZA AUTOMÁTICA DE ÓRDENES PENDIENTES OBSOLETAS POR CANT. MONEDAS ACTIVAS ──
    try:
        open_fx_res = supabase.table('forex_positions').select('symbol').eq('status', 'open').execute()
        active_fx_symbols = set(p['symbol'] for p in (open_fx_res.data or []))
        
        open_crypto_res = supabase.table('positions').select('symbol').eq('status', 'open').execute()
        active_crypto_symbols = set(p['symbol'] for p in (open_crypto_res.data or []))
        
        tc_res = supabase.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
        tc_data = tc_res.data if tc_res and tc_res.data else {}
        reg_params = tc_data.get('regime_params', {}) or {}
        max_fx = int(reg_params.get('max_active_symbols_forex', 1))
        max_crypto = int(reg_params.get('max_active_symbols_crypto', 1))

        # Si Forex ya alcanzó el límite de monedas activas, cancelar órdenes pendientes para otros pares de Forex
        if len(active_fx_symbols) >= max_fx:
            other_fx = [s for s in ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD'] if s not in active_fx_symbols]
            if other_fx:
                supabase.table('pending_orders').update({
                    'status': 'cancelled',
                    'rejection_reason': 'max_active_symbols',
                    'cancelled_at': datetime.now(timezone.utc).isoformat(),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).in_('symbol', other_fx).eq('status', 'pending').execute()
                log_info('SWING', f"🧹 [MATA-ZOMBIES FOREX] Canceladas órdenes pendientes obsoletas de pares no permitidos: {other_fx}")

        # Si Crypto ya alcanzó el límite de monedas activas, cancelar órdenes pendientes para otras cryptos
        if len(active_crypto_symbols) >= max_crypto:
            all_pend = supabase.table('pending_orders').select('id, symbol').eq('status', 'pending').execute()
            forex_list = {'EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD'}
            other_crypto_ids = [p['id'] for p in (all_pend.data or []) if p['symbol'] not in forex_list and p['symbol'] not in active_crypto_symbols]
            if other_crypto_ids:
                supabase.table('pending_orders').update({
                    'status': 'cancelled',
                    'rejection_reason': 'max_active_symbols',
                    'cancelled_at': datetime.now(timezone.utc).isoformat(),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }).in_('id', other_crypto_ids).execute()
                log_info('SWING', f"🧹 [MATA-ZOMBIES CRYPTO] Canceladas {len(other_crypto_ids)} órdenes pendientes de cryptos inactivas.")
    except Exception as cleanup_err:
        log_error('SWING', f"Error en limpia-zombies de monedas activas: {cleanup_err}")

    # ── 2. CONTROL DE MÁXIMO GLOBAL DE LÍMITES POR MODO ──
    res = supabase.table('pending_orders').select('*').eq('status', 'pending').eq('mode', mode).execute()
    pending = res.data or []
    if len(pending) >= max_limits:
        q_map = {'high': 3, 'medium': 2, 'low': 1}
        pending_sorted = sorted(pending, key=lambda x: (q_map.get(x.get('signal_quality', 'low'), 1), x.get('created_at', '')))
        to_cancel_count = len(pending) - max_limits + 1
        to_cancel = pending_sorted[:to_cancel_count]
        for order in to_cancel:
            supabase.table('pending_orders').update({
                'status': 'cancelled',
                'rejection_reason': 'max_limits',
                'cancelled_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }).eq('id', order['id']).execute()
            log_info('SWING', f"Mata-Zombies: Cancelled {order['symbol']} limit to free margin. (Q: {order.get('signal_quality')})")

async def create_smart_limit_order(symbol, direction, limit_price, sl_price, tp1_price, tp2_price, band_target, sizing_pct, movement_type, signal_quality, fib_zone_entry, ttl_hours, supabase):
    # Enforce Global Limit Max before creating new one
    mode = 'paper' if BOT_STATE.config_cache.get("paper_trading", False) else 'real'
    await enforce_global_limit_max(supabase, mode, max_limits=5)

    # Truncate strings to avoid DB length errors (varchar 10)
    safe_trade_type = "smart_lim"  # 9 chars
    safe_movement = (movement_type or "unknown")[:10]
    
    new_order = {
        'symbol': symbol, 'direction': direction, 'order_type': 'limit', 'trade_type': safe_trade_type,
        'rule_code': 'SMART' if direction == 'long' else 'SMART_S',
        'limit_price': limit_price, 'sl_price': sl_price, 'tp1_price': tp1_price, 'tp2_price': tp2_price,
        'band_name': band_target, 'status': 'pending',
        'mode': 'paper' if BOT_STATE.config_cache.get("paper_trading", False) else 'real',
        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat(),
        'sizing_pct': sizing_pct, 'timeframe': '15m',
        'movement_type': safe_movement, 'signal_quality': signal_quality, 'fib_zone_entry': fib_zone_entry
    }
    supabase.table('pending_orders').insert(new_order).execute()

async def check_limit_order_execution(symbol: str, current_price: float, provider, sb) -> None:
    is_paper = BOT_STATE.config_cache.get("paper_trading", False)
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

        # --- DYNAMIC CANCELLATION Aa21/Bb21 & SMART Trend Limits ---
        rule_code = order.get('rule_code', '')
        mov_type = order.get('movement_type', '')
        if '21' in rule_code or 'ApexEma' in rule_code or 'trend' in str(mov_type):
            try:
                from app.core.memory_store import get_memory_df
                df_15m_mem = get_memory_df(symbol, "15m")
                if df_15m_mem is not None and not df_15m_mem.empty and len(df_15m_mem) >= 5:
                    ema3_15m = df_15m_mem['close'].ewm(span=3, adjust=False).mean()
                    ema9_15m = df_15m_mem['close'].ewm(span=9, adjust=False).mean()
                    curr_ema3 = float(ema3_15m.iloc[-1])
                    curr_ema9 = float(ema9_15m.iloc[-1])
                    if direction == 'long' and curr_ema3 < curr_ema9:
                        log_info('SWING', f"[Aa21 CANCELED] Tendencia LONG rota (EMA3 < EMA9 en 15m). Cancelando orden para {symbol}.")
                        await cancel_swing_orders(symbol, reason='aa21_trend_break', sb=sb, direction=direction)
                        continue
                    if direction == 'short' and curr_ema3 > curr_ema9:
                        log_info('SWING', f"[Bb21 CANCELED] Tendencia SHORT rota (EMA3 > EMA9 en 15m). Cancelando orden para {symbol}.")
                        await cancel_swing_orders(symbol, reason='bb21_trend_break', sb=sb, direction=direction)
                        continue
            except Exception as e:
                pass
        # ---------------------------------------

        if not price_hit: continue

        # --- REAL-TIME MOMENTUM GUARD ---
        try:
            # Bypass 1m momentum guard for Trend Pullback strategies (Aa21/Bb21) 
            # because pullbacks naturally have 1m downtrend when reaching the entry price
            if '21' not in rule_code:
                df_1m = await provider.get_ohlcv(symbol=symbol, timeframe='1m', limit=20)
                if df_1m is not None and not df_1m.empty and len(df_1m) >= 10:
                    df_1m['ema3'] = df_1m['close'].ewm(span=3, adjust=False).mean()
                    df_1m['ema9'] = df_1m['close'].ewm(span=9, adjust=False).mean()
                    ema3_1m = float(df_1m.iloc[-1]['ema3'])
                    ema9_1m = float(df_1m.iloc[-1]['ema9'])
                    
                    if direction == 'long' and ema3_1m < ema9_1m:
                        log_warning('SWING', f"[MOMENTUM GUARD] Orden Límite cancelada en tiempo real. {symbol} LONG pero EMA3 ({ema3_1m:.4f}) < EMA9 ({ema9_1m:.4f}) mid-candle.")
                        await cancel_swing_orders(symbol, timeframe=order.get('timeframe', ''), reason='realtime_momentum_reversal', sb=sb, direction=direction)
                        continue
                    if direction == 'short' and ema3_1m > ema9_1m:
                        log_warning('SWING', f"[MOMENTUM GUARD] Orden Límite cancelada en tiempo real. {symbol} SHORT pero EMA3 ({ema3_1m:.4f}) > EMA9 ({ema9_1m:.4f}) mid-candle.")
                        await cancel_swing_orders(symbol, timeframe=order.get('timeframe', ''), reason='realtime_momentum_reversal', sb=sb, direction=direction)
                        continue
        except Exception as e:
            log_warning('SWING', f"No se pudo verificar momentum en 1m para {symbol}: {e}")
        # ---------------------------------

        log_info('SWING', f'{symbol}: LIMIT EJECUTADO {direction.upper()} @ ${current_price:,.4f}')
        if is_paper:
            await execute_limit_order_paper(order=order, execution_price=current_price, sb=sb)
        else:
            await execute_limit_order_real(order=order, execution_price=current_price, binance_client=provider, sb=sb)

async def execute_limit_order_paper(order: dict, execution_price: float, sb) -> None:
    symbol = order['symbol']
    direction = order['direction']
    
    is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF'))
    table_name = 'forex_positions' if is_forex else 'positions'

    async with BOT_STATE.order_lock:
        try:
            # 1. Límite Global (Fail-Closed)
            max_global = int(BOT_STATE.config_cache.get('max_open_trades', 15))
            try:
                pos_res = sb.table(table_name).select('id', count='exact').eq('status', 'open').limit(0).execute()
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
                sym_pos_res = sb.table(table_name).select('id, rule_code, opened_at, entry_price, side', count='exact').in_('symbol', variants).eq('status', 'open').execute()
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
                hist = sb.table(table_name).select('opened_at').in_('symbol', variants).eq('rule_code', rule_code).gte('opened_at', since).order('opened_at', desc=True).limit(1).execute()
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
            opp_res = sb.table(table_name).select('*').in_('symbol', variants).eq('status', 'open').execute()
            to_close = [p for p in (opp_res.data or []) if (p.get('side') or '').upper() == opposite_side]
            if to_close:
                from app.execution.order_manager import close_position
                for p_close in to_close:
                    close_position(p_close['id'], reason=f"reversal_swing_{direction.lower()}")
        except Exception as rev_e:
            log_warning('SWING', f"Error reversión: {rev_e}")

        # 4. Apertura
        try:
            resolved_market_type = 'forex_futures' if is_forex else 'crypto_futures'

            from app.core.position_sizing import calculate_position_size
            sizing = calculate_position_size(
                symbol=symbol, entry_price=execution_price, 
                sl_price=float(order.get('sl_price') or 0),
                market_type=resolved_market_type,
                trade_number=1, regime='swing', supabase=sb
            )
            qty = sizing['quantity'] if sizing else 0
            if qty <= 0: return
            
            # Apply sizing percentage (T1/T2 distribution or reentry split)
            sizing_pct = float(order.get('sizing_pct') or 1.0)
            qty = qty * sizing_pct
            
            # For Forex, convert quantity from raw units to standard lots (1 lot = 100,000 units)
            if is_forex:
                qty = qty / 100000.0
                qty = max(round(qty, 2), 0.01) # Round to 2 decimals, floor at 0.01 lots
            else:
                qty = round(qty, 4)
                
            if qty <= 0: return

            sb.table('pending_orders').update({'status': 'triggered', 'triggered_at': datetime.now(timezone.utc).isoformat()}).eq('id', order['id']).execute()
            
            # ═══════════════════════════════════════════════════════════
            # ATOMIC LIMIT CHECK — LAST LINE OF DEFENSE BEFORE INSERT
            # Re-query DB right before INSERT to catch any concurrent opens
            # ═══════════════════════════════════════════════════════════
            final_variants = crypto_symbol_match_variants(symbol)
            final_count_res = sb.table(table_name).select('id', count='exact').in_('symbol', final_variants).eq('status', 'open').limit(0).execute()
            final_count = final_count_res.count if final_count_res.count is not None else 999
            if final_count >= max_symbol:
                log_warning('SWING', f"🚫 ATOMIC BLOCK: {symbol} has {final_count} open (max {max_symbol}). Swing INSERT rejected.")
                return

            # Validar de forma atómica el límite de monedas activas simultáneas (Cant. Monedas Activas)
            all_active_res = sb.table(table_name).select('symbol').eq('status', 'open').execute()
            active_unique_syms = set(p['symbol'] for p in (all_active_res.data or []))
            
            tc_res = sb.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
            tc_data = tc_res.data if tc_res and tc_res.data else {}
            reg_params = tc_data.get('regime_params', {}) or {}
            max_active_syms = int(reg_params.get('max_active_symbols_forex' if is_forex else 'max_active_symbols_crypto', 1))

            if symbol not in active_unique_syms and len(active_unique_syms) >= max_active_syms:
                log_warning('SWING', f"🚫 ATOMIC BLOCK MONEDAS ACTIVAS: {symbol} omitido. Ya hay {len(active_unique_syms)}/{max_active_syms} monedas activas ({list(active_unique_syms)}). Swing INSERT rechazado.")
                return
            # ═══════════════════════════════════════════════════════════

            if is_forex:
                pos_data = {
                    'symbol': symbol, 'side': direction.upper(), 'entry_price': execution_price,
                    'sl_price': float(order.get('sl_price') or 0),
                    'tp_price': float(order.get('tp2_price') or 0), 'status': 'open', 'lots': qty,
                    'current_price': execution_price, 'opened_at': datetime.now(timezone.utc).isoformat(),
                    'mode': 'paper', 'rule_code': order.get('rule_code', 'SWING'),
                    'market_type': resolved_market_type,
                }
                import hashlib
                uuid_hash = int(hashlib.md5(str(order.get('id', '')).encode()).hexdigest(), 16) % (2**63 - 1)
                pos_data['ctrader_order_id'] = uuid_hash
            else:
                pos_data = {
                    'symbol': symbol, 'side': direction.upper(), 'entry_price': execution_price,
                    'avg_entry_price': execution_price, 'stop_loss': float(order.get('sl_price') or 0),
                    'take_profit': float(order.get('tp2_price') or 0), 'status': 'open', 'size': qty,
                    'current_price': execution_price, 'opened_at': datetime.now(timezone.utc).isoformat(),
                    'mode': 'paper', 'rule_code': order.get('rule_code', 'SWING'),
                    'market_type': resolved_market_type
                }
                
            res = sb.table(table_name).insert(pos_data).execute()
            if res.data:
                p = res.data[0]
                # Key by pos_id to support multiple positions per symbol
                BOT_STATE.positions[p.get('id', symbol)] = p
                log_info('SWING', f"🚀 POSICIÓN ABIERTA: {symbol} {direction.upper()} (ID: {p.get('id')})")
        except Exception as e:
            log_error('SWING', f"Error abriendo posición swing: {e}")

async def execute_limit_order_real(order, execution_price, binance_client, sb):
    log_info('SWING', f"{order['symbol']}: Real mode execution not implemented here.")
