import asyncio
from app.core.supabase_client import get_supabase

async def verify():
    sb = get_supabase()
    
    # Check variables
    v_res = sb.table('strategy_variables').select('id,name,source_field').in_('id', [101, 102, 103, 104]).execute()
    print("VARS:", v_res.data)
    
    # Check conditions
    c_res = sb.table('strategy_conditions').select('id,name').in_('id', [201, 202, 203, 204]).execute()
    print("CONDS:", c_res.data)
    
    # Check Rule Dd61_15m
    r61 = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Dd61_15m').single().execute()
    print("DD61_15m:", r61.data['condition_ids'], r61.data['condition_weights'])

    # Check Rule Dd51_15m
    r51 = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Dd51_15m').single().execute()
    print("DD51_15m:", r51.data['condition_ids'], r51.data['condition_weights'])

if __name__ == "__main__":
    asyncio.run(verify())
