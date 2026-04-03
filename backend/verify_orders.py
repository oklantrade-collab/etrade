import os
from dotenv import load_dotenv
from supabase import create_client
import sys

# Cargar .env manualmente si no esta en path
load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def check_orders():
    try:
        # 1. Query general para historial (ultimas 20)
        res = sb.table('pending_orders').select('symbol, direction, band_name, limit_price, status, created_at, triggered_at, cancelled_at').order('created_at', desc=True).limit(20).execute()
        
        print("\n--- HISTORIAL DE ÓRDENES (Últimas 20) ---")
        if not res.data:
            print("No se encontraron órdenes en la tabla.")
        else:
            header = f"{'Symbol':<10} | {'Side':<6} | {'Limit':<10} | {'Status':<10} | {'Created At':<20}"
            print(header)
            print("-" * len(header))
            for o in res.data:
                limit = float(o['limit_price']) if o['limit_price'] else 0
                created = o['created_at'][:19] if o['created_at'] else "-"
                print(f"{o['symbol']:<10} | {o['direction']:<6} | {limit:<10.4f} | {o['status']:<10} | {created:<20}")

        # 2. Query de órdenes pendientes actualmente activas
        res_p = sb.table('pending_orders').select('symbol, direction, trade_type, rule_code, band_name, limit_price, sl_price, tp1_price, tp2_price, status, expires_at, created_at').eq('status', 'pending').order('created_at', desc=True).execute()
        
        print("\n--- ÓRDENES PENDIENTES ACTUALMENTE ACTIVAS ---")
        if not res_p.data:
            print("No hay órdenes pendientes en este momento.")
        else:
            header_p = f"{'Symbol':<10} | {'Rule':<6} | {'Limit':<10} | {'SL':<10} | {'TP1':<10} | {'TP2':<10}"
            print(header_p)
            print("-" * len(header_p))
            for o in res_p.data:
                limit = float(o['limit_price']) if o['limit_price'] else 0
                sl = float(o['sl_price']) if o['sl_price'] else 0
                tp1 = float(o['tp1_price']) if o['tp1_price'] else 0
                tp2 = float(o['tp2_price']) if o['tp2_price'] else 0
                print(f"{o['symbol']:<10} | {o['rule_code']:<6} | {limit:<10.4f} | {sl:<10.4f} | {tp1:<10.4f} | {tp2:<10.4f}")

    except Exception as e:
        print(f"Error consultando Supabase: {e}")

if __name__ == "__main__":
    check_orders()
