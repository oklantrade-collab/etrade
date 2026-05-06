import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def list_tables():
    sb = get_supabase()
    # This is not direct, but we can try to access some common ones or use a query
    # Usually we can't list all tables via the client easily without RPC or similar.
    # But I'll try to check if 'forex_trades' exists.
    try:
        res = sb.table("forex_trades").select("*").limit(1).execute()
        print("forex_trades exists")
    except:
        print("forex_trades does not exist")

    try:
        res = sb.table("forex_journal").select("*").limit(1).execute()
        print("forex_journal exists")
    except:
        print("forex_journal does not exist")

if __name__ == "__main__":
    asyncio.run(list_tables())
