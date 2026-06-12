import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.supabase_client import get_supabase

async def check_apex():
    sb = get_supabase()
    res = sb.table("stocks_config").select("*").eq("key", "apex_min_opportunities").execute()
    print("Config:", res.data)
    
    # Check if there are any opportunities at all
    opps = sb.table("trade_opportunities").select("*").limit(5).execute()
    print("Sample opps:", opps.data)

if __name__ == "__main__":
    asyncio.run(check_apex())
