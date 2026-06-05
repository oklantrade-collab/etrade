import asyncio
from app.core.supabase_client import get_supabase

async def add_rules():
    sb = get_supabase()
    
    # 1. Ensure variables exist
    # First, get existing variables
    res_vars = sb.table('strategy_variables').select('id, source_field').execute()
    existing_vars = {v['source_field']: v['id'] for v in res_vars.data}
    max_var_id = max([v['id'] for v in res_vars.data]) if res_vars.data else 0

    var_bb_expanding_id = existing_vars.get('bb_expanding')
    if not var_bb_expanding_id:
        max_var_id += 1
        var_bb_expanding_id = max_var_id
        sb.table('strategy_variables').insert({
            'id': var_bb_expanding_id,
            'name': 'Bollinger Expanding',
            'category': 'technical',
            'source_field': 'bb_expanding',
            'data_type': 'boolean',
            'description': 'BB Expanding (Sup up, Inf down)',
            'enabled': True
        }).execute()
        print(f"Inserted variable bb_expanding with ID {var_bb_expanding_id}")

    # 2. Get existing conditions to avoid duplicates
    res_conds = sb.table('strategy_conditions').select('id, name').execute()
    existing_cond_names = {c['name']: c['id'] for c in res_conds.data}
    max_cond_id = max([c['id'] for c in res_conds.data]) if res_conds.data else 0

    conditions_to_add = [
        {
            'name': 'EMA3 < EMA9',
            'variable_id': existing_vars['ema3'],
            'operator': '<',
            'value_type': 'variable',
            'value_variable': 'ema9',
            'description': 'Checks if EMA3 < EMA9',
            'enabled': True
        },
        {
            'name': 'EMA9 < EMA20',
            'variable_id': existing_vars['ema9'],
            'operator': '<',
            'value_type': 'variable',
            'value_variable': 'ema20',
            'description': 'Checks if EMA9 < EMA20',
            'enabled': True
        },
        {
            'name': 'EMA20 < EMA50',
            'variable_id': existing_vars['ema20'],
            'operator': '<',
            'value_type': 'variable',
            'value_variable': 'ema50',
            'description': 'Checks if EMA20 < EMA50',
            'enabled': True
        },
        {
            'name': 'PRECIO EN ZONA LOWER_2 O SUPERIOR 5 MIN',
            'variable_id': existing_vars['price'],
            'operator': '>=',
            'value_type': 'variable',
            'value_variable': 'lower_2',
            'description': 'Price >= lower_2',
            'enabled': True
        },
        {
            'name': 'BANDA SUP_UP INF_DOW 15MIN',
            'variable_id': var_bb_expanding_id,
            'operator': '==',
            'value_type': 'literal',
            'value_literal': 'True',
            'description': 'Donde la banda superior de Bollinger se abre positivamente hacia arriba y se abre la banda inferior de Bollinger negativamente hacia abajo',
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
