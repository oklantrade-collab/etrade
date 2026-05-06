import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_gdc_monitor():
    sb = get_supabase()
    # Search for GDC in messages, but filter by module position_monitor
    res = sb.table("system_logs").select("*").eq("module", "position_monitor").ilike("message", "%GDC%").order("created_at", desc=True).limit(10).execute()
    for log in res.data:
        print(f"[{log['created_at']}] {log['message']}")

if __name__ == "__main__":
    asyncio.run(check_gdc_monitor())
