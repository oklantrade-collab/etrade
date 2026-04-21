import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def find_xau_hidden():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').execute()
    xau = [p for p in res.data if p['symbol'] and 'XAU' in p['symbol'].upper()]
    print(f"XAU related in forex_positions: {len(xau)}")
    for p in xau:
        print(f"ID: {p['id']}, Symbol: {repr(p['symbol'])}, Status: {repr(p['status'])}, PNL: {p.get('pnl_usd')}")

if __name__ == "__main__":
    asyncio.run(find_xau_hidden())
