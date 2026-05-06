import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_rules_in_db():
    sb = get_supabase()
    try:
        res = sb.table("trading_rules").select("*").eq("rule_code", "Dd51").execute()
        print(f"Rule Dd51 found: {len(res.data)}")
        for r in res.data:
            print(f"Name: {r['name']} | ID: {r['id']} | Enabled: {r['enabled']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_rules_in_db())
