import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_all_forex():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').order('opened_at', desc=True).limit(100).execute()
    print(f"Total forex positions fetched: {len(res.data)}")
    for p in res.data:
        print(f"ID: {p['id']}, Symbol: {p['symbol']}, Status: {p['status']}, Lots: {p['lots']}, PNL: {p.get('pnl_usd')}, Opened: {p.get('opened_at')}")

if __name__ == "__main__":
    asyncio.run(check_all_forex())
