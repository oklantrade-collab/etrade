import asyncio
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
load_dotenv('backend/.env')

from app.core.supabase_client import get_supabase

async def check_logs():
    sb = get_supabase()
    print("Checking last system_logs...")
    try:
        res = sb.table("system_logs")\
            .select("*")\
            .order("created_at", desc=True)\
            .limit(20)\
            .execute()
        for row in res.data:
            print(f"[{row['created_at']}] {row['module']} - {row['level']}: {row['message']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_logs())
