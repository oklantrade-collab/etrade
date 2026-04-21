import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_all_positions():
    sb = get_supabase()
    res = sb.table('positions').select('symbol, status, created_at, pnl_usd').execute()
    print("--- ALL POSITIONS SYMBOLS ---")
    if res.data:
        symbols = set(p['symbol'] for p in res.data)
        print(f"Symbols found: {symbols}")
        # Count XAUUSD
        xau_pos = [p for p in res.data if 'XAU' in p['symbol']]
        print(f"XAU related positions count: {len(xau_pos)}")
        for p in xau_pos[:10]: # Print first 10
             print(p)
    else:
        print("No positions found in 'positions' table.")

if __name__ == "__main__":
    asyncio.run(check_all_positions())
