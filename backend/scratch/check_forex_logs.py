import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_forex_logs():
    sb = get_supabase()
    res = sb.table("system_logs").select("*").ilike("message", "%GBPUSD%").order("created_at", desc=True).limit(20).execute()
    for log in res.data:
        print(f"[{log['created_at']}] {log['message']}")

if __name__ == "__main__":
    asyncio.run(check_forex_logs())
