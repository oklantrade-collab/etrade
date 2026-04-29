import asyncio
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_positions():
    sb = get_supabase()
    res = sb.table('stocks_positions').select('*').eq('status', 'open').execute()
    print(f"--- OPEN POSITIONS ({len(res.data)}) ---")
    for r in res.data:
        print(f"{r['ticker']} | Entry: {r['avg_price']} | Shares: {r['shares']}")
    
    res2 = sb.table('stocks_config').select('*').execute()
    print("\n--- STOCKS CONFIG ---")
    for r in res2.data:
        print(f"{r['key']}: {r['value']}")

if __name__ == "__main__":
    asyncio.run(check_positions())
