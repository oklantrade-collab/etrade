import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def list_open_forex():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('status', 'open').execute()
    print(f"Open positions count: {len(res.data)}")
    for p in res.data:
        print(f"ID: {p['id']}, Symbol: {p['symbol']}, Status: {p['status']}, PNL: {p.get('pnl_usd')}")

if __name__ == "__main__":
    asyncio.run(list_open_forex())
