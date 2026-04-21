import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_candle_positions():
    sb = get_supabase()
    try:
        res = sb.table('candle_positions').select('*').limit(10).execute()
        print(f"Table 'candle_positions' exists. Found {len(res.data)} rows.")
        for r in res.data:
            print(r)
    except Exception as e:
        print(f"Table 'candle_positions' does not exist or error: {e}")

if __name__ == "__main__":
    asyncio.run(check_candle_positions())
