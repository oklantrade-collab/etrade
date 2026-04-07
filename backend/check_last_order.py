import asyncio
import os
import sys
from app.core.supabase_client import get_supabase

# Añadir el path base para importar app
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def check_last_order():
    sb = get_supabase()
    # Check last buy orders
    res = sb.table('orders').select('*').eq('side', 'BUY').order('created_at', desc=True).limit(5).execute()
    print("--- ULTIMAS COMPRAS (ORDERS) ---")
    if not res.data:
        print("No buy orders found.")
        return
        
    for o in res.data:
        print(f"Time: {o['created_at']} | Symbol: {o['symbol']} | Rule: {o.get('rule_code')} | Status: {o.get('status')}")

if __name__ == "__main__":
    asyncio.run(check_last_order())
