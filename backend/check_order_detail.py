import asyncio
import os
import sys
from app.core.supabase_client import get_supabase

# Añadir el path base para importar app
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def check_order_detail():
    sb = get_supabase()
    res = sb.table('orders').select('*, sl_price, tp_price').eq('symbol', 'ADAUSDT').order('created_at', desc=True).limit(3).execute()
    print("--- ADAUSDT ORDERS DETAIL ---")
    for o in res.data:
        print(f"ID: {o['id']} | Rule: {o.get('rule_code')} | Entry: {o.get('price')} | SL: {o.get('sl_price')} | TP: {o.get('tp_price')}")

if __name__ == "__main__":
    asyncio.run(check_order_detail())
