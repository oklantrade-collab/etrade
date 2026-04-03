import asyncio
from app.core.supabase_client import get_supabase

async def check_rules_id():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('id, rule_code').eq('rule_code', 'Aa12').execute()
    print(res.data)

if __name__ == "__main__":
    asyncio.run(check_rules_id())
