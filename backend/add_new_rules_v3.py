import asyncio
from app.core.supabase_client import get_supabase

async def add_rules():
    sb = get_supabase()
    
    # 1. Get existing conditions to avoid duplicates
    res_conds = sb.table('strategy_conditions').select('id, name').execute()
    existing_cond_names = {c['name']: c['id'] for c in res_conds.data}
    max_cond_id = max([c['id'] for c in res_conds.data]) if res_conds.data else 0

    conditions_to_add = [
        {
            'name': 'LONG LOW UNDER EMA9 15MIN',
            'variable_id': 1, # price
            'operator': '<=',
            'value_type': 'variable',
            'value_variable': 'ema9',
            'description': 'Price <= EMA9 in 15min',
            'enabled': True
        },
        {
            'name': 'LONG LOW UNDER EMA20 15MIN',
            'variable_id': 1, # price
            'operator': '<=',
            'value_type': 'variable',
            'value_variable': 'ema20',
            'description': 'Price <= EMA20 in 15min',
            'enabled': True
        },
        {
            'name': 'SHORT HIGH OVER EMA9 15MIN',
            'variable_id': 1, # price
            'operator': '>=',
            'value_type': 'variable',
            'value_variable': 'ema9',
            'description': 'Price >= EMA9 in 15min',
            'enabled': True
        },
        {
            'name': 'SHORT HIGH OVER EMA20 15MIN',
            'variable_id': 1, # price
            'operator': '>=',
            'value_type': 'variable',
            'value_variable': 'ema20',
            'description': 'Price >= EMA20 in 15min',
            'enabled': True
        }
    ]

    for cond in conditions_to_add:
        if cond['name'] not in existing_cond_names:
            max_cond_id += 1
            cond['id'] = max_cond_id
            sb.table('strategy_conditions').insert(cond).execute()
            print(f"Inserted condition: {cond['name']} with ID {max_cond_id}")
        else:
            print(f"Condition {cond['name']} already exists.")

asyncio.run(add_rules())
