import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def find_xau_positions():
    sb = get_supabase()
    # Try case insensitive search
    res = sb.table('positions').select('symbol, is_open, pnl_usd').ilike('symbol', '%XAU%').execute()
    print("--- XAU RELATED POSITIONS ---")
    if res.data:
        print(f"Found {len(res.data)} positions.")
        for p in res.data[:20]:
            print(p)
    else:
        print("No XAU related positions found in 'positions' table.")

if __name__ == "__main__":
    asyncio.run(find_xau_positions())
