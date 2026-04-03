import asyncio
from app.core.supabase_client import get_supabase

async def get_aa12():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa12').execute()
    for r in res.data:
        print(f"ID: {r['id']} | Code: {r['rule_code']} | Name: {r['name']} | Cycle: {r['cycle']} | Conditions: {r['condition_ids']}")

if __name__ == "__main__":
    asyncio.run(get_aa12())
