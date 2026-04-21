import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_orders():
    sb = get_supabase()
    res = sb.table('orders').select('*').ilike('symbol', '%XAU%').execute()
    print(f"Total XAU orders: {len(res.data)}")
    for o in res.data[:10]:
        print(f"ID: {o['id']}, Symbol: {o['symbol']}, Status: {o['status']}, PNL: {o.get('pnl')}")

if __name__ == "__main__":
    asyncio.run(check_orders())
