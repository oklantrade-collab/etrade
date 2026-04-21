import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_all_xau():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').execute()
    print(f"XAUUSD count: {len(res.data)}")
    for p in res.data:
        print(f"ID: {p['id']}, PNL: {p.get('pnl_usd')}, Status: {p['status']}, Lots: {p.get('lots')}")

if __name__ == "__main__":
    asyncio.run(check_all_xau())
