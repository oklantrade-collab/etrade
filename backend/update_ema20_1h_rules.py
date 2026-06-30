import asyncio
from app.core.supabase_client import get_supabase

async def update_rules():
    sb = get_supabase()
    
    variables = [
        {
            "id": 63,
            "name": "ema20_descending_1h",
            "description": "EMA20 en modo descendente en 1h",
            "source_field": "ema20_descending_1h",
            "category": "combined",
            "enabled": True
        },
        {
            "id": 64,
            "name": "ema20_ascending_1h",
            "description": "EMA20 en modo ascendente en 1h",
            "source_field": "ema20_ascending_1h",
            "category": "combined",
            "enabled": True
        }
    ]
    for var in variables:
        sb.table('strategy_variables').upsert(var).execute()
        
    conditions = [
        {
            "id": 73,
            "name": "EMA20 Descendiendo 1h",
            "variable_id": 63,
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "id": 74,
            "name": "EMA20 Ascendiendo 1h",
            "variable_id": 64,
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
        # Remove old condition 72 and add new condition 74
        c_ids = [c for c in rule['condition_ids'] if c != 72]
        c_ids = list(set(c_ids + [74]))
        w = round(1.0 / len(c_ids), 3)
        c_weights = {str(c): w for c in c_ids}
        sb.table('strategy_rules_v2').update({'condition_ids': c_ids, 'condition_weights': c_weights}).eq('id', rule['id']).execute()
        print("Updated Aa13 to use EMA20 1H ascending")
        
    # Update Bb13
    bb13_res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Bb13').execute()
    if bb13_res.data:
        rule = bb13_res.data[0]
        # Remove old condition 71 and add new condition 73
        c_ids = [c for c in rule['condition_ids'] if c != 71]
        c_ids = list(set(c_ids + [73]))
        w = round(1.0 / len(c_ids), 3)
        c_weights = {str(c): w for c in c_ids}
        sb.table('strategy_rules_v2').update({'condition_ids': c_ids, 'condition_weights': c_weights}).eq('id', rule['id']).execute()
        print("Updated Bb13 to use EMA20 1H descending")

if __name__ == "__main__":
    asyncio.run(update_rules())
