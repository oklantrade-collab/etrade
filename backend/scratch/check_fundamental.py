import asyncio
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_fundamental(ticker):
    sb = get_supabase()
    res = sb.table('fundamental_cache').select('*').eq('ticker', ticker).execute()
    if res.data:
        s = res.data[0]
        print(f"--- {ticker} FUNDAMENTAL ---")
        print(f"Fundamental Score: {s.get('fundamental_score')}")
        print(f"IA Score: {s.get('ia_score')}")
        print(f"Intrinsic: {s.get('composite_intrinsic')}")
        print(f"Refreshed: {s.get('refreshed_at')}")
    else:
        print(f"No fundamental data for {ticker}")

if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "DRCT"
    asyncio.run(check_fundamental(ticker))
