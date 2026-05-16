import asyncio
import os
import sys
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    res = sb.table("system_logs")\
            .select("*")\
            .or_("module.eq.pipeline,module.eq.candle_signal_exec")\
            .order("created_at", desc=True)\
            .limit(50)\
            .execute()
    print(json.dumps(res.data, indent=2))

if __name__ == "__main__":
    asyncio.run(check())
