import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def debug_forex():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').execute()
    print(f"Total forex positions: {len(res.data)}")
    if res.data:
        symbols = set(p['symbol'] for p in res.data)
        print(f"Forex symbols: {symbols}")
        xau = [p for p in res.data if p['symbol'] == 'XAUUSD']
        print(f"XAUUSD count: {len(xau)}")
        for p in xau[:5]:
            print(f"ID: {p['id']}, PNL: {p.get('pnl_usd')}")

if __name__ == "__main__":
    asyncio.run(debug_forex())
