import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_stocks_logs():
    sb = get_supabase()
    res = sb.table("system_logs").select("*").ilike("module", "%stocks%").order("created_at", desc=True).limit(50).execute()
    for row in res.data:
        print(f"[{row['created_at']}] {row['module']} | {row['level']} | {row['message']}")

if __name__ == "__main__":
    asyncio.run(check_stocks_logs())
