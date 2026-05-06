import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_rules_v2():
    sb = get_supabase()
    try:
        res = sb.table("strategy_rules_v2").select("*").eq("rule_code", "Dd51").execute()
        print(f"Rule Dd51 in v2: {len(res.data)}")
        for r in res.data:
            print(f"Name: {r['name']} | ID: {r['id']} | Enabled: {r['enabled']}")
            print(f"Conditions IDs: {r.get('condition_ids')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_rules_v2())
