import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase
from datetime import datetime, timezone, timedelta

async def check_recent_diagnostics():
    sb = get_supabase()
    since = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    try:
        res = sb.table("pilot_diagnostics").select("*").gte("timestamp", since).order("timestamp", desc=True).limit(10).execute()
        print(f"Recent diagnostics entries: {len(res.data)}")
        for r in res.data:
            print(f"[{r['timestamp']}] Symbol: {r['symbol']} | Msg: {r['error_message']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_recent_diagnostics())
