import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_rules():
    sb = get_supabase()
    res = sb.table("stocks_rules").select("*").eq("direction", "sell").eq("enabled", True).execute()
    for rule in res.data:
        print(f"Rule: {rule['rule_code']}, Order: {rule['order_type']}")

if __name__ == "__main__":
    asyncio.run(check_rules())
