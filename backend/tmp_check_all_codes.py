import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def dump_all():
    sb = get_supabase()
    rules = sb.table('strategy_rules_v2').select('id, rule_code, applicable_cycles').execute().data
    print(json.dumps(rules, indent=2))
if __name__ == "__main__":
    asyncio.run(dump_all())
