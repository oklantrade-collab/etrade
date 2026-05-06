import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def debug_dd51_v2():
    sb = get_supabase()
    try:
        res = sb.table("strategy_rules_v2").select("*").ilike("rule_code", "%Dd51%").execute()
        for r in res.data:
            print(f"Rule Code: '{r['rule_code']}' | Name: '{r['name']}'")
            print(f"Condition IDs: {r.get('condition_ids')}")
            print(f"Min Score: {r.get('min_score')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_dd51_v2())
