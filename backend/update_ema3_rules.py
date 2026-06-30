import asyncio
from app.core.supabase_client import get_supabase

async def update_rules():
    sb = get_supabase()
    
    variables = [
        {
            "id": 61,
            "name": "ema3_descending_15m",
            "description": "EMA3 en modo descendente en 15m",
            "source_field": "ema3_descending_15m",
            "category": "combined",
            "enabled": True
        },
        {
            "id": 62,
            "name": "ema3_ascending_15m",
            "description": "EMA3 en modo ascendente en 15m",
            "source_field": "ema3_ascending_15m",
            "category": "combined",
            "enabled": True
        }
    ]
    for var in variables:
        sb.table('strategy_variables').upsert(var).execute()
        
    conditions = [
        {
            "id": 71,
            "name": "EMA3 Descendiendo 15m",
            "variable_id": 61,
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "id": 72,
            "name": "EMA3 Ascendiendo 15m",
            "variable_id": 62,
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        }
    ]
    for cond in conditions:
        sb.table('strategy_conditions').upsert(cond).execute()
        
    # Update Aa13
    aa13_res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa13').execute()
    if aa13_res.data:
        rule = aa13_res.data[0]
        c_ids = list(set(rule['condition_ids'] + [72]))
        w = round(1.0 / len(c_ids), 3)
        c_weights = {str(c): w for c in c_ids}
        sb.table('strategy_rules_v2').update({'condition_ids': c_ids, 'condition_weights': c_weights}).eq('id', rule['id']).execute()
        print("Updated Aa13")
        
    # Update Bb13
    bb13_res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Bb13').execute()
    if bb13_res.data:
        rule = bb13_res.data[0]
        c_ids = list(set(rule['condition_ids'] + [71]))
        w = round(1.0 / len(c_ids), 3)
        c_weights = {str(c): w for c in c_ids}
        sb.table('strategy_rules_v2').update({'condition_ids': c_ids, 'condition_weights': c_weights}).eq('id', rule['id']).execute()
        print("Updated Bb13")

if __name__ == "__main__":
    asyncio.run(update_rules())
