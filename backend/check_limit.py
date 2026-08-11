import asyncio
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    risk = sb.table('risk_config').select('*').limit(1).execute()
    print('Risk Config:', risk.data)
    r = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa30C').execute()
    print('Rule Aa30C:', r.data)

if __name__ == '__main__':
    asyncio.run(check())
