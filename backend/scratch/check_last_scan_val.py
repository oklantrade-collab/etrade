import asyncio
import os
import sys
from datetime import datetime

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_scores():
    sb = get_supabase()
    res = sb.table("technical_scores").select("*").order("timestamp", desc=True).limit(5).execute()
    print(f"Current UTC time: {datetime.utcnow().isoformat()}")
    if res.data:
        for row in res.data:
            sigs = row.get('signals_json', {})
            print(f"Ticker: {row['ticker']}, Last Scan Time: {sigs.get('last_scan_time')}")
    else:
        print("No data in technical_scores")

if __name__ == "__main__":
    asyncio.run(check_scores())
