import logging
from datetime import datetime
from binance.exceptions import BinanceAPIException

from app.core.crypto_symbols import (
    normalize_crypto_symbol,
    resolve_crypto_position_quantity,
    crypto_symbol_match_variants,
)

def round_price(price: float, tick_size: float) -> float:
    import math
    if tick_size <= 0: return price
    precision = int(round(-math.log(tick_size, 10), 0))
    return round(price - (price % tick_size), precision)

def loguear(level, msg):
    if level == logging.CRITICAL:
        logging.critical(msg)
    elif level == logging.WARNING:
        logging.warning(msg)
    else:
        logging.info(msg)

def execute_trade(
    signal: dict,
    oco_params: dict,
    cycle_id: str,
    supabase_client,
    binance_client
) -> dict | None:

    # PASO 1 — Crear registro de orden en Supabase (status='pending')
    try:
        sym_norm = normalize_crypto_symbol(oco_params['symbol'])
        order_record = supabase_client.table('orders').insert({
            'signal_id': signal['signal_id'],
            'symbol': sym_norm,
            'side': oco_params['side'],
            'order_type': 'MARKET',
            'quantity': oco_params['quantity'],
            'stop_loss_price': oco_params['stop_loss'],
            'take_profit_price': oco_params['take_profit'],
            'status': 'pending'
        }).execute()
        
        if not order_record.data:
            return None
            
        order_id = order_record.data[0]['id']
    except Exception as e:
        loguear(logging.CRITICAL, f'Fail saving pending order: {e}')
        return None

    # PASO 2 — Ejecutar orden de ENTRADA (MARKET)
    try:
        if oco_params['side'] == 'BUY':
            entry_order = binance_client.order_market_buy(
                symbol=sym_norm,
                quantity=oco_params['quantity']
            )
        else:
            entry_order = binance_client.order_market_sell(
                symbol=sym_norm,
                quantity=oco_params['quantity']
            )
            
    except BinanceAPIException as e:
        # Si la entrada falla → marcar orden como error y retornar
        try:
            supabase_client.table('orders').update({
                'status': 'error',
                'updated_at': datetime.utcnow().isoformat()
            }).eq('id', order_id).execute()
        except:
            pass
            
        loguear(logging.CRITICAL, f'Entry order FAILED: {e}')
        return None

    # Extraer precio real de ejecución
    fills = entry_order.get('fills', [])
    if fills:
        avg_fill_price = sum(
            float(f['price']) * float(f['qty']) for f in fills
        ) / sum(float(f['qty']) for f in fills)
        commission = sum(float(f['commission']) for f in fills)
    else:
        avg_fill_price = oco_params['entry_price']
        commission = 0.0

    exchange_order_id = str(entry_order['orderId'])

    # Actualizar orden con datos de ejecución
    supabase_client.table('orders').update({
        'exchange_order_id': exchange_order_id,
        'entry_price': avg_fill_price,
        'commission': commission,
        'status': 'open'
    }).eq('id', order_id).execute()

    # PASO 3 — Recalcular SL y TP con precio real de ejecución
    price_diff = avg_fill_price - oco_params['entry_price']
    sl_price_final = oco_params['stop_loss'] + price_diff
    tp_price_final = oco_params['take_profit'] + price_diff

    # Find tick size using symbol info
    try:
        info = binance_client.get_symbol_info(sym_norm)
        tick_size = 0.01
        for f in info['filters']:
            if f['filterType'] == 'PRICE_FILTER':
                tick_size = float(f['tickSize'])
    except:
        tick_size = 0.01

    sl_price_final = round_price(sl_price_final, tick_size)
    tp_price_final = round_price(tp_price_final, tick_size)
    sl_limit_final = round_price(
        sl_price_final * (0.998 if oco_params['side'] == 'BUY' else 1.002),
        tick_size
    )

    # PASO 4 — Colocar OCO Order (SL + TP juntos)
    oco_side = 'SELL' if oco_params['side'] == 'BUY' else 'BUY'
    oco_list_id = None

    try:
        oco_order = binance_client.create_oco_order(
            symbol=sym_norm,
            side=oco_side,
            quantity=oco_params['quantity'],
            price=str(tp_price_final),
            stopPrice=str(sl_price_final),
            stopLimitPrice=str(sl_limit_final),
            stopLimitTimeInForce='GTC'
        )
        oco_list_id = str(oco_order.get('orderListId', ''))
        
        # Actualizar orden con OCO ID
        supabase_client.table('orders').update({
            'oco_list_client_id': oco_list_id,
            'stop_loss_price': sl_price_final,
            'take_profit_price': tp_price_final,
            'status': 'open'
        }).eq('id', order_id).execute()
        
    except BinanceAPIException as e:
        loguear(logging.CRITICAL, 
            f'⚠️ OCO FAILED para {sym_norm}. Posición abierta SIN SL/TP: {e}')
        
        supabase_client.table('alert_events').insert({
            'event_type': 'oco_failed',
            'symbol': sym_norm,
            'message': f'OCO ORDER FAILED - posición sin protección: {str(e)}',
            'severity': 'critical',
            'data': { 'order_id': order_id, 'error': str(e) }
        }).execute()
        
        # Intentar colocar solo el stop loss como fallback
        try:
            if oco_side == 'SELL':
                binance_client.create_order(
                    symbol=sym_norm,
                    side='SELL',
                    type='STOP_LOSS_LIMIT',
                    quantity=oco_params['quantity'],
                    price=str(sl_limit_final),
                    stopPrice=str(sl_price_final),
                    timeInForce='GTC'
                )
                loguear(logging.WARNING, 'Fallback SL colocado exitosamente')
            else:
                binance_client.create_order(
                    symbol=sym_norm,
                    side='BUY',
                    type='STOP_LOSS_LIMIT',
                    quantity=oco_params['quantity'],
                    price=str(sl_limit_final),
                    stopPrice=str(sl_price_final),
                    timeInForce='GTC'
                )
                loguear(logging.WARNING, 'Fallback SL colocado exitosamente')
        except:
            loguear(logging.CRITICAL, 'Fallback SL también falló. Intervención manual requerida.')

    # PASO 5 — Obtener niveles Fibonacci finales de market_snapshot
    try:
        snap_res = supabase_client.table('market_snapshot').select('*').eq('symbol', sym_norm).single().execute()
        snap = snap_res.data or {}
        if oco_params['side'] == 'BUY':
            tp_partial = snap.get('upper_5', tp_price_final * 0.98) # fallback if snap missing
            tp_full    = snap.get('upper_6', tp_price_final)
        else:
            tp_partial = snap.get('lower_5', tp_price_final * 1.02)
            tp_full    = snap.get('lower_6', tp_price_final)
    except:
        tp_partial = tp_price_final * (0.98 if oco_params['side'] == 'BUY' else 1.02)
        tp_full    = tp_price_final

    # FINAL STEP — Crear registro en positions
    position = supabase_client.table('positions').insert({
        'order_id': order_id,
        'symbol': sym_norm,
        'side': 'LONG' if oco_params['side'] == 'BUY' else 'SHORT',
        'entry_price': avg_fill_price,
        'avg_entry_price': avg_fill_price,
        'current_price': avg_fill_price,
        'size': oco_params['quantity'],
        'stop_loss': sl_price_final,
        'sl_price': sl_price_final,
        'take_profit': tp_full,
        'tp_partial_price': tp_partial,
        'tp_full_price': tp_full,
        'unrealized_pnl': 0.0,
        'realized_pnl': 0.0,
        'status': 'open',
        'regime_entry': signal.get('regime', 'riesgo_medio'),
        'rule_code': signal.get('rule_code'),
        'rule_entry': signal.get('rule_code'),
        'opened_at': datetime.utcnow().isoformat()
    }).execute()

    # PASO 6 — Actualizar estado de la señal
    try:
        supabase_client.table('trading_signals').update({
            'status': 'executed'
        }).eq('id', signal['signal_id']).execute()
    except Exception as e:
        loguear(logging.WARNING, f"Could not update status of signal to executed: {e}")

    # RETORNO
    return {
        'order_id': order_id,
        'exchange_order_id': exchange_order_id,
        'oco_list_id': oco_list_id,
        'symbol': sym_norm,
        'side': oco_params['side'],
        'quantity': oco_params['quantity'],
        'entry_price': avg_fill_price,
        'stop_loss': sl_price_final,
        'take_profit': tp_price_final,
        'commission': commission,
        'rr_ratio': oco_params.get('risk_reward_ratio', 2.5)
    }

def close_all_positions(supabase, client):
    # 1. Obtener todas las posiciones con status='open'
    open_positions = supabase.table('positions').select('*, orders(oco_list_client_id)').eq('status', 'open').execute()
    if not open_positions.data:
        return
        
    for pos in open_positions.data:
        symbol = normalize_crypto_symbol(pos['symbol'])
        oco_client_id = pos.get('orders', {}).get('oco_list_client_id')
        
        # a. Cancelar la OCO order en Binance si existe:
        if oco_client_id:
            try:
                # To find the orderListId we typically have to query it or pass orderListId.
                # If oco_client_id is the string ID we can pass it as listClientOrderId
                client.cancel_order_list(symbol=symbol, listClientOrderId=oco_client_id)
            except Exception as e:
                loguear(logging.WARNING, f"Could not cancel OCO for {symbol}: {e}")
                
        # b. Enviar orden MARKET de cierre:
        try:
            side_to_close = 'SELL' if pos['side'] == 'LONG' else 'BUY'
            if side_to_close == 'SELL':
                client.order_market_sell(symbol=symbol, quantity=pos['size'])
            else:
                client.order_market_buy(symbol=symbol, quantity=pos['size'])
        except Exception as e:
            loguear(logging.CRITICAL, f"Market order to close {symbol} failed: {e}")
            
        # c. Actualizar position: status='closed', close_reason='KILL_SWITCH', closed_at=now
        try:
            supabase.table('positions').update({
                'status': 'closed',
                'close_reason': 'KILL_SWITCH',
                'closed_at': datetime.utcnow().isoformat()
            }).eq('id', pos['id']).execute()
        except:
            pass

def close_position(position_id: str, reason: str = "MANUAL") -> bool:
    from app.core.supabase_client import get_supabase
    from app.execution.binance_connector import get_client
    from app.core.logger import log_info, log_error, log_warning

    try:
        sb = get_supabase()
        log_info("ORDER_MANAGER", f"Requesting MANUAL CLOSE for position {position_id}")
        
        pos_resp = sb.table("positions").select("*, orders(oco_list_client_id)").eq("id", position_id).execute()
        if not pos_resp.data:
            log_error("ORDER_MANAGER", f"Position {position_id} not found in DB.")
            return False

        position = pos_resp.data[0]
        binance_symbol = normalize_crypto_symbol(position["symbol"])
        qty = resolve_crypto_position_quantity(sb, position)
        if qty <= 0:
            log_error("ORDER_MANAGER", f"Position {position_id} has zero size; cannot close on exchange.")
            return False
        
        # Guard against position['orders'] being None (if no order_id exists)
        orders_data = position.get('orders') or {}
        oco_client_id = orders_data.get('oco_list_client_id')
        
        side = "SELL" if position["side"] == "LONG" else "BUY"

        # --- SOPORTE PAPER TRADING (v4.0) ---
        from app.core.memory_store import BOT_STATE
        is_paper = BOT_STATE.config_cache.get("paper_trading", True) is not False

        if is_paper:
            # En PAPER simplemente simulamos el cierre con el precio actual
            avg_fill_price = float(position.get("current_price") or position.get("entry_price") or 0)
            log_info("ORDER_MANAGER", f"Manual close in PAPER mode for {binance_symbol} at {avg_fill_price}")
        else:
            client = get_client()

            if oco_client_id:
                try:
                    client.cancel_order_list(symbol=binance_symbol, listClientOrderId=oco_client_id)
                except Exception as e:
                    log_warning("ORDER_MANAGER", f"Could not cancel OCO for {binance_symbol}: {e}")

            try:
                if side == "SELL":
                    close_order = client.order_market_sell(symbol=binance_symbol, quantity=float(qty))
                else:
                    close_order = client.order_market_buy(symbol=binance_symbol, quantity=float(qty))

                fills = close_order.get('fills', [])
                if fills:
                    avg_fill_price = sum(float(f['price']) * float(f['qty']) for f in fills) / sum(float(f['qty']) for f in fills)
                else:
                    avg_fill_price = float(position["current_price"])
            except Exception as e:
                log_error("ORDER_MANAGER", f"Binance close order FAILED: {e}")
                return False
            
        # Calulamos el PnL según el lado de la posición (Case-Insensitive)
        if position['side'].upper() in ['LONG', 'BUY']:
            realized_pnl = (avg_fill_price - float(position['entry_price'])) * float(qty)
        else:
            realized_pnl = (float(position['entry_price']) - avg_fill_price) * float(qty)

        entry_p = float(position['entry_price'] or 0)
        notional = entry_p * float(qty)
        pnl_pct = round((realized_pnl / notional * 100), 4) if notional > 0 else 0.0

        sb.table("positions").update({
            "status": "closed",
            "symbol": binance_symbol,
            "size": qty,
            "close_reason": reason[:50], # Guard against long reasons
            "realized_pnl": round(float(realized_pnl), 4),
            "realized_pnl_pct": pnl_pct,
            "current_price": avg_fill_price,
            "closed_at": datetime.utcnow().isoformat(),
        }).eq("id", position_id).execute()

        if position.get("order_id"):
            sb.table("orders").update({
                "status": "manual_close",
                "closed_at": datetime.utcnow().isoformat(),
            }).eq("id", position["order_id"]).execute()

        # ── CANCELAR ÓRDENES HUÉRFANAS ──
        # Cancelar cualquier pending_order y order abierto del símbolo
        try:
            now_iso = datetime.utcnow().isoformat()
            for sym_v in crypto_symbol_match_variants(binance_symbol):
                sb.table("pending_orders").update({
                    "status": "cancelled",
                    "cancelled_at": now_iso,
                    "updated_at": now_iso
                }).eq("symbol", sym_v).eq("status", "pending").execute()
                sb.table("orders").update({
                    "status": "manual_close",
                    "closed_at": now_iso
                }).eq("symbol", sym_v).eq("status", "open").execute()
            log_info("ORDER_MANAGER", f"🧹 Órdenes pendientes canceladas para {binance_symbol}")
        except Exception as cancel_e:
            log_warning("ORDER_MANAGER", f"Error cancelando órdenes huérfanas: {cancel_e}")

        log_info("ORDER_MANAGER", f"Position {position_id} ({binance_symbol}) closed manually with PnL: {realized_pnl:.4f}")
        return True

    except Exception as e:
        from app.core.logger import log_error
        log_error("ORDER_MANAGER", f"CRITICAL: Failed to close position {position_id}: {e}")
        return False

