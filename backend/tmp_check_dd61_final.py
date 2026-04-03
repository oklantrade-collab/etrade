import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def dump_dd61():
    sb = get_supabase()
    rules = sb.table('strategy_rules_v2').select('*').ilike('rule_code', 'Dd61%').execute().data
    print(json.dumps(rules, indent=2))
if __name__ == "__main__":
    asyncio.run(dump_dd61())
