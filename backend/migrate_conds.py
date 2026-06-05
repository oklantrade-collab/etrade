import asyncio
from app.core.supabase_client import get_supabase

async def migrate():
    sb = get_supabase()
    
    # 1. Asegurar que price y upper_2 existan como variables
    vars_needed = ['price', 'upper_2']
    var_ids = {}
    
    res_vars = sb.table('strategy_variables').select('*').execute()
    existing_vars = {v['source_field']: v['id'] for v in res_vars.data}
    max_var_id = max([v['id'] for v in res_vars.data]) if res_vars.data else 0
    
    for v in vars_needed:
        if v in existing_vars:
            var_ids[v] = existing_vars[v]
        else:
            max_var_id += 1
            ins = sb.table('strategy_variables').insert({
                'id': max_var_id,
                'name': v.upper(),
                'source_field': v,
                'data_type': 'float',
                'description': f'{v.upper()} line',
                'enabled': True
            }).execute()
            var_ids[v] = ins.data[0]['id']

    # 2. Crear la condicion PRECIO EN ZONA UPPER_2 O INFERIOR 5 MIN
    cond_name = 'PRECIO EN ZONA UPPER_2 O INFERIOR 5 MIN'
    
    res_conds = sb.table('strategy_conditions').select('id, name').execute()
    existing_cond_names = {c['name']: c['id'] for c in res_conds.data}
    max_cond_id = max([c['id'] for c in res_conds.data]) if res_conds.data else 0
    
    if cond_name not in existing_cond_names:
        max_cond_id += 1
        sb.table('strategy_conditions').insert({
            'id': max_cond_id,
            'name': cond_name,
            'variable_id': var_ids['price'],
            'operator': '<=',
            'value_type': 'variable',
            'value_variable': 'upper_2',
            'description': 'Price <= upper_2',
            'enabled': True
        }).execute()
        print(f"Inserted condition: {cond_name} with ID {max_cond_id}")
    else:
        print(f"Condition {cond_name} already exists.")

    # 3. Actualizar la regla Aa21
    res_rule = sb.table('strategy_rules_v2').select('rule_code, applicable_cycles').eq('rule_code', 'Aa21').execute()
    if res_rule.data:
        cycles = res_rule.data[0].get('applicable_cycles') or ['15m']
        if '5m' not in cycles:
            cycles.append('5m')
            sb.table('strategy_rules_v2').update({'applicable_cycles': cycles}).eq('rule_code', 'Aa21').execute()
            print(f"Updated Aa21 applicable_cycles to: {cycles}")
        else:
            print(f"Aa21 already has 5m in cycles: {cycles}")
    else:
        print("Rule Aa21 not found!")

asyncio.run(migrate())
