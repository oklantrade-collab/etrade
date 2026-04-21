import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_forex_orders():
    sb = get_supabase()
    res = sb.table('forex_orders').select('*').ilike('symbol', '%XAU%').execute()
    print(f"XAU related in forex_orders: {len(res.data)}")
    for o in res.data[:10]:
        print(f"ID: {o['id']}, Symbol: {o['symbol']}, Status: {o['status']}, PNL: {o.get('pnl_usd')}")

if __name__ == "__main__":
    asyncio.run(check_forex_orders())
