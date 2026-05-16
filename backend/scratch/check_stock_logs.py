import asyncio
import os
import sys
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    from datetime import datetime, timedelta, timezone
    five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    res = sb.table("system_logs")\
            .select("*")\
            .ilike("module", "%stock%")\
            .gte("created_at", five_min_ago)\
            .order("created_at", desc=True)\
            .execute()
    print(json.dumps(res.data, indent=2))

if __name__ == "__main__":
    asyncio.run(check())
