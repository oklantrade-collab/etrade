import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_trading_config():
    sb = get_supabase()
    try:
        res = sb.table("trading_config").select("*").eq("id", 1).single().execute()
        print(f"Trading Config: {res.data}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_trading_config())
