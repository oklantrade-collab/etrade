import logging
from datetime import datetime, timezone

from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_warning, log_error

MODULE = "EMERGENCY_GUARDS"

async def trigger_emergency_protection(market_type: str):
    """
    Se ejecuta cuando se activa un bloqueo de seguridad en el market especificado
    (crypto_futures o forex_futures).
    Aplica la Estrategia OCO Segura de Breakeven.
    """
    log_warning(MODULE, f"🚨 INICIANDO PROTECCIÓN DE EMERGENCIA PARA {market_type.upper()}")
    sb = get_supabase()
    
    try:
        # Obtener todas las posiciones abiertas del mercado especificado
        # Asumimos que forex_futures guarda en 'forex_positions' y crypto en 'positions'
        table_name = 'forex_positions' if 'forex' in market_type else 'positions'
        res = sb.table(table_name).select('*').eq('status', 'open').execute()
        open_positions = res.data or []
        
        if not open_positions:
            log_info(MODULE, f"No hay posiciones abiertas en {market_type} para proteger.")
            return

        for pos in open_positions:
            pos_id = pos['id']
            symbol = pos['symbol']
            side = pos.get('side', '').upper()
            entry_price = float(pos.get('entry_price') or pos.get('avg_entry_price') or 0)
            current_price = float(pos.get('current_price') or entry_price)
            
            # Calcular PNL
            if side in ['LONG', 'BUY']:
                pnl = current_price - entry_price
            else:
                pnl = entry_price - current_price
                
            # Condición A: PNL >= 0 -> Cerrar a Mercado
            if pnl >= 0:
                log_info(MODULE, f"[{symbol}] PNL >= 0. Cerrando a mercado por emergencia.")
                if 'forex' in market_type:
                    # Marcar para cierre en la BD (el worker intentará cerrarla si puede)
                    sb.table(table_name).update({
                        'status': 'closed',
                        'close_reason': 'EMERGENCY_PROFIT_CLOSE',
                        'closed_at': datetime.now(timezone.utc).isoformat()
                    }).eq('id', pos_id).execute()
                else:
                    from app.execution.order_manager import close_position
                    success = close_position(pos_id, "EMERGENCY_PROFIT_CLOSE")
                    if not success:
                        log_error(MODULE, f"[{symbol}] Falló el cierre de emergencia.")
                
            # Condición B: PNL < 0 -> Establecer Take Profit Limit en Breakeven (Estrategia OCO)
            else:
                log_info(MODULE, f"[{symbol}] PNL < 0. Colocando TP Limit de Breakeven a {entry_price}.")
                # Actualizar el take_profit en BD usando columnas existentes
                update_data = {
                    'recovery_exit_reason': 'EMERGENCY_OCO',
                }
                if 'forex' in market_type:
                    update_data['tp_price'] = entry_price
                    update_data['recovery_target_price'] = pos.get('tp_price')
                else:
                    update_data['take_profit'] = entry_price
                    update_data['tp_full_price'] = entry_price
                    update_data['protection_status'] = 'EMERGENCY_OCO'
                    update_data['recovery_target_price'] = pos.get('take_profit') or pos.get('tp_full_price')
                    
                sb.table(table_name).update(update_data).eq('id', pos_id).execute()
                
                # Para Crypto en Binance Live, re-crear la OCO si es necesario
                if 'crypto' in market_type:
                    try:
                        from app.core.memory_store import BOT_STATE
                        is_paper = BOT_STATE.config_cache.get("paper_trading", True) is not False
                        if not is_paper:
                            # Cancelar OCO anterior y crear nueva
                            from app.execution.binance_connector import get_client
                            client = get_client()
                            # Extraer ID OCO anterior si existe
                            oco_id = None
                            sl_price = float(pos.get('sl_price') or pos.get('stop_loss') or 0)
                            
                            if 'order_id' in pos:
                                order_res = sb.table('orders').select('oco_list_client_id, stop_loss_price').eq('id', pos['order_id']).execute()
                                if order_res.data:
                                    oco_id = order_res.data[0].get('oco_list_client_id')
                                    if not sl_price:
                                        sl_price = float(order_res.data[0].get('stop_loss_price') or 0)
                            
                            if oco_id:
                                try:
                                    client.cancel_order_list(symbol=symbol, listClientOrderId=oco_id)
                                except Exception as cancel_err:
                                    log_warning(MODULE, f"No se pudo cancelar OCO previa para {symbol}: {cancel_err}")
                            
                            # Si tenemos SL, colocar nueva OCO
                            if sl_price and sl_price > 0:
                                qty = pos.get('size')
                                oco_side = 'SELL' if side in ['LONG', 'BUY'] else 'BUY'
                                
                                # Conseguir tick_size
                                try:
                                    info = client.get_symbol_info(symbol)
                                    tick_size = 0.01
                                    for f in info['filters']:
                                        if f['filterType'] == 'PRICE_FILTER':
                                            tick_size = float(f['tickSize'])
                                except:
                                    tick_size = 0.01
                                
                                import math
                                precision = int(round(-math.log(tick_size, 10), 0)) if tick_size < 1 else 0
                                
                                tp_final = round(entry_price - (entry_price % tick_size), precision)
                                sl_final = round(float(sl_price) - (float(sl_price) % tick_size), precision)
                                sl_limit = round(sl_final * (0.998 if oco_side == 'SELL' else 1.002), precision)
                                
                                new_oco = client.create_oco_order(
                                    symbol=symbol,
                                    side=oco_side,
                                    quantity=qty,
                                    price=str(tp_final),
                                    stopPrice=str(sl_final),
                                    stopLimitPrice=str(sl_limit),
                                    stopLimitTimeInForce='GTC'
                                )
                                new_oco_id = str(new_oco.get('orderListId', ''))
                                sb.table('orders').update({
                                    'oco_list_client_id': new_oco_id,
                                    'take_profit_price': tp_final
                                }).eq('id', pos.get('order_id')).execute()
                                log_info(MODULE, f"Nueva orden OCO de Emergencia colocada en Binance para {symbol}.")
                    except Exception as e:
                        log_error(MODULE, f"Error colocando OCO de emergencia para {symbol}: {e}")

        log_info(MODULE, f"Protección de emergencia completada para {market_type}.")
    except Exception as e:
        log_error(MODULE, f"Error crítico en trigger_emergency_protection: {e}")

async def restore_emergency_protection(market_type: str):
    """
    Restaura las posiciones que estaban en modo de emergencia una vez que el
    bloqueo se levanta.
    """
    log_info(MODULE, f"✅ LEVANTANDO PROTECCIÓN DE EMERGENCIA PARA {market_type.upper()}")
    sb = get_supabase()
    
    try:
        table_name = 'forex_positions' if 'forex' in market_type else 'positions'
        if 'forex' in market_type:
            res = sb.table(table_name).select('*').eq('status', 'open').eq('recovery_exit_reason', 'EMERGENCY_OCO').execute()
        else:
            res = sb.table(table_name).select('*').eq('status', 'open').eq('protection_status', 'EMERGENCY_OCO').execute()
            
        protected_positions = res.data or []
        
        for pos in protected_positions:
            pos_id = pos['id']
            symbol = pos['symbol']
            original_tp = pos.get('recovery_target_price')
            
            # Restaurar el TP original en la base de datos
            update_data = {
                'recovery_exit_reason': None,
                'recovery_target_price': None
            }
            if 'forex' in market_type:
                update_data['tp_price'] = original_tp
            else:
                update_data['protection_status'] = None
                update_data['take_profit'] = original_tp
                update_data['tp_full_price'] = original_tp
                
            sb.table(table_name).update(update_data).eq('id', pos_id).execute()
            
            # No recreamos la OCO original en Live porque los workers normales (profit_ladder, adaptive_tp) 
            # se encargarán de actualizarla en su próximo ciclo natural (lo cual es más robusto).
            log_info(MODULE, f"[{symbol}] TP Limit de Breakeven cancelado. Delegando al worker normal.")
            
    except Exception as e:
        log_error(MODULE, f"Error crítico restaurando protección: {e}")
