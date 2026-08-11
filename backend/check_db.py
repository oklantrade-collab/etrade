import asyncio
from app.core.supabase_client import get_supabase
import json

async def check():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa23').execute()
    if res.data:
        rule = res.data[0]
        print('Rule details:', json.dumps(rule, indent=2))
        
        cond_ids = rule['condition_ids']
        cond_res = sb.table('strategy_conditions').select('id,name').in_('id', cond_ids).execute()
        print('\nConditions:')
        for c in cond_res.data:
            print(f"ID: {c['id']}, Name: {c['name']}")
            
if __name__ == '__main__':
    asyncio.run(check())
