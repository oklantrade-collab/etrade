import asyncio
from app.core.supabase_client import get_supabase
import json

async def fetch_aa21():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa21').execute()
    if not res.data:
        print("Aa21 not found in DB.")
        return
        
    rule = res.data[0]
    print('Rule details for Aa21:', json.dumps({k:v for k,v in rule.items() if k not in ['created_at', 'updated_at']}, indent=2))
    
    cond_ids = rule['condition_ids']
    cond_res = sb.table('strategy_conditions').select('id,name,description,operator,value_literal').in_('id', cond_ids).execute()
    
    print('\nConditions:')
    for c in cond_res.data:
        weight = rule['condition_weights'].get(str(c['id']), 0)
        print(f"- ID: {c['id']} | Name: {c['name']} | Weight: {weight} | Desc: {c['description']}")

if __name__ == '__main__':
    asyncio.run(fetch_aa21())
