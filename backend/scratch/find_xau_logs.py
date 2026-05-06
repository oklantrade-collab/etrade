import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def find_xau_logs():
    sb = get_supabase()
    res = sb.table('system_logs').select('*').ilike('message', '%XAUUSD%').order('created_at', desc=True).limit(50).execute()
    for row in res.data:
        print(f"[{row['created_at']}] {row['level']} | {row['message']}")

if __name__ == "__main__":
    asyncio.run(find_xau_logs())
