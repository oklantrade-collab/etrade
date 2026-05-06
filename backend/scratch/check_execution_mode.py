import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_execution_mode():
    sb = get_supabase()
    res = sb.table("stocks_config").select("*").eq("key", "execution_mode").execute()
    if res.data:
        print(f"Execution Mode: {res.data[0]['value']}")
    else:
        print("Execution Mode not set (Default: paper)")

if __name__ == "__main__":
    asyncio.run(check_execution_mode())
