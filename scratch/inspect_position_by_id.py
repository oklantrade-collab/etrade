import os
import sys

# Agregar backend al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    ids = ['d54f58e2-73aa-4272-8f34-8e7aed3c868a', 'd24a3768-e38f-4063-b27e-5985f5f3ef0f']
    print("--- DETALLE DE LAS POSICIONES ---")
    for pid in ids:
        p_res = sb.table('positions').select('*').eq('id', pid).execute()
        if p_res.data:
            p = p_res.data[0]
            print(f"Position ID: {p.get('id')}")
            print(f"  Symbol: {p.get('symbol')} | Side: {p.get('side')} | Size: {p.get('size')} | Status: {p.get('status')}")
            print(f"  Entry Price: {p.get('entry_price')} | Current Price: {p.get('current_price')}")
            print(f"  Opened At: {p.get('opened_at')} | Closed At: {p.get('closed_at')}")
            print(f"  Close Reason: {p.get('close_reason')} | Realized PNL: {p.get('realized_pnl')}")
            print(f"  Order ID: {p.get('order_id')}")
            
            # Buscar la orden
            oid = p.get('order_id')
            if oid:
                o_res = sb.table('orders').select('*').eq('id', oid).execute()
                if o_res.data:
                    o = o_res.data[0]
                    print(f"  Order Details:")
                    print(f"    Exchange Order ID: {o.get('exchange_order_id')}")
                    print(f"    Status: {o.get('status')}")
                    print(f"    Created At: {o.get('created_at')} | Closed At: {o.get('closed_at')}")
                    print(f"    OCO List Client ID: {o.get('oco_list_client_id')}")
                else:
                    print("  No order found in orders table for this order_id.")
            else:
                print("  No order_id associated with this position.")
        else:
            print(f"Position {pid} not found.")
        print("-" * 60)

if __name__ == '__main__':
    main()
