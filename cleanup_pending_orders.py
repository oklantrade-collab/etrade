"""
Script de limpieza: Cancela órdenes pending_fill atascadas en Binance y DB.
Ejecutar una sola vez después de deployar los fixes.

Uso: python cleanup_pending_orders.py
"""
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from dotenv import load_dotenv
load_dotenv()

def main():
    from app.core.supabase_client import get_supabase
    from app.execution.binance_connector import get_client
    from app.core.crypto_symbols import normalize_crypto_symbol
    
    sb = get_supabase()
    client = get_client()
    
    # 1. Obtener todas las órdenes pending_fill
    orders = sb.table('orders').select('*, positions(*)').eq('status', 'pending_fill').execute()
    
    if not orders.data:
        print("✅ No hay órdenes pending_fill. Todo limpio.")
        return
    
    print(f"🔍 Encontradas {len(orders.data)} órdenes pending_fill:\n")
    
    for o in orders.data:
        symbol = normalize_crypto_symbol(o['symbol'])
        order_id = o.get('exchange_order_id', '')
        print(f"  📋 Order DB#{o['id']} | {symbol} | {o['side']} | Qty: {o['quantity']} | Exchange: {order_id}")
        
        # 2. Intentar cancelar en Binance
        if order_id:
            try:
                exchange_order = client.get_order(symbol=symbol, orderId=int(order_id))
                binance_status = exchange_order['status']
                print(f"     Binance status: {binance_status}")
                
                if binance_status in ('NEW', 'PARTIALLY_FILLED'):
                    try:
                        client.cancel_order(symbol=symbol, orderId=int(order_id))
                        print(f"     ✅ Cancelada en Binance")
                    except Exception as e:
                        print(f"     ⚠️ Error cancelando en Binance: {e}")
                elif binance_status == 'FILLED':
                    print(f"     ⚠️ ATENCIÓN: Esta orden SÍ se llenó en Binance! Verificar manualmente.")
                    continue  # No tocar la DB, necesita revisión manual
                else:
                    print(f"     ℹ️ Ya está {binance_status} en Binance")
            except Exception as e:
                print(f"     ⚠️ Error consultando Binance: {e}")
        
        # 3. Actualizar DB
        sb.table('orders').update({'status': 'cancelled'}).eq('id', o['id']).execute()
        print(f"     ✅ Order DB actualizada a 'cancelled'")
        
        # 4. Cerrar posición asociada
        if o.get('positions') and len(o['positions']) > 0:
            pos_id = o['positions'][0]['id']
            sb.table('positions').update({
                'status': 'closed',
                'close_reason': 'cleanup_pending_fill'
            }).eq('id', pos_id).execute()
            print(f"     ✅ Position {pos_id} cerrada con reason='cleanup_pending_fill'")
    
    print(f"\n✅ Limpieza completada. {len(orders.data)} órdenes procesadas.")
    
    # 5. Verificar si safety_blocked_crypto está activo
    tc = sb.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
    if tc and tc.data:
        params = tc.data.get('regime_params', {}) or {}
        if params.get('safety_blocked_crypto', False):
            print("\n⚠️  ATENCIÓN: safety_blocked_crypto está en TRUE!")
            resp = input("¿Deseas resetearlo a False? (y/n): ")
            if resp.lower() == 'y':
                params['safety_blocked_crypto'] = False
                sb.table('trading_config').update({'regime_params': params}).eq('id', 1).execute()
                print("✅ safety_blocked_crypto reseteado a False")
        else:
            print("\n✅ safety_blocked_crypto = False (OK)")
        
        max_active = params.get('max_active_symbols_crypto', 'NOT SET')
        print(f"ℹ️  max_active_symbols_crypto = {max_active}")

if __name__ == '__main__':
    main()
