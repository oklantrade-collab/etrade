import asyncio
from app.core.supabase_client import get_supabase

async def check_conditions():
    sb = get_supabase()
    
    # Get all variables
    res_vars = sb.table('strategy_variables').select('*').execute()
    variables = {v['source_field']: v['id'] for v in res_vars.data}
    
    # Get all conditions
    res_cond = sb.table('strategy_conditions').select('*').execute()
    
    # Map source_field to condition ID (assuming we want operator == 1 or similar)
    cond_map = {}
    for c in res_cond.data:
        var_id = c['variable_id']
        # find variable source field
        source_field = None
        for v in res_vars.data:
            if v['id'] == var_id:
                source_field = v['source_field']
                break
        
        if source_field:
            if source_field not in cond_map:
                cond_map[source_field] = []
            cond_map[source_field].append(c)

    print("--- CONDITION MAP ---")
    keys_to_check = [
        'ema9_above_ema20_15m',
        'ema9_5m', # Might be different, let's search for ema9
        'ema3_5m',
        'ema20_ascending_1h',
        'bb_upper_ascending_15m',
        'sar_trend_15m',
        'fresh_cross_long',
        'ema20_angle_5m'
    ]
    
    for k in keys_to_check:
        print(f"Checking exact: {k}")
        if k in cond_map:
            for c in cond_map[k]:
                print(f"  FOUND: CondID={c['id']} Name='{c['name']}' Op={c['operator']} Val={c['value_literal']}")
        else:
            print(f"  NOT FOUND exact match for {k}")

    print("\n--- ALL VARIABLES ---")
    for v in res_vars.data:
        sf = str(v.get('source_field', '')).lower()
        if 'ema9' in sf or 'ema3' in sf or 'ema20' in sf or 'sar' in sf or 'cross' in sf or 'angle' in sf:
            print(f"Var: {v['source_field']} (ID: {v['id']}) - {v['name']}")

if __name__ == "__main__":
    asyncio.run(check_conditions())
