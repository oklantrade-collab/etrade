import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_all_positions_v2():
    sb = get_supabase()
    res = sb.table('positions').select('symbol, status, is_open').execute()
    print(f"Total positions in 'positions' table: {len(res.data)}")
    symbols = set(p['symbol'] for p in res.data)
    print(f"Symbols: {symbols}")
    open_pos = [p for p in res.data if p['is_open']]
    print(f"Open positions count: {len(open_pos)}")
    for p in open_pos[:10]:
        print(p)

if __name__ == "__main__":
    asyncio.run(check_all_positions_v2())
