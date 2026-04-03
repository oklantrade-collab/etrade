import os
import asyncio
import json
from app.core.supabase_client import get_supabase

async def check_rules():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('*').execute()
    for r in res.data:
        print(f"Code: {r['rule_code']} | Name: {r['name']} | Type: {r['strategy_type']} | Cycle: {r['cycle']}")

if __name__ == "__main__":
    asyncio.run(check_rules())
