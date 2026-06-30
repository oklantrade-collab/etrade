import asyncio
from app.core.supabase_client import get_supabase

async def update_dip_rules():
    sb = get_supabase()
    
    # 1. Add variable
    var = {
        "id": 65,
        "name": "low_below_ema20_15m",
        "description": "El LOW cruza o está debajo de la EMA20 (DIP)",
        "source_field": "low_below_ema20_15m",
        "category": "combined",
        "enabled": True
    }
    sb.table('strategy_variables').upsert(var).execute()
    
    # 2. Add condition
    cond = {
        "id": 75,
        "name": "LOW < EMA20 (15m) (DIP)",
        "variable_id": 65,
        "operator": "==",
        "value_type": "literal",
        "value_literal": 1,
        "enabled": True
    }
    sb.table('strategy_conditions').upsert(cond).execute()
    
    # 3. Update Aa23
    res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa23').execute()
    if res.data:
        rule = res.data[0]
        c_ids = list(set(rule['condition_ids'] + [75, 2])) # 75 = DIP, 2 = EMA9 > EMA20
        w = round(1.0 / len(c_ids), 3)
        c_weights = {str(c): w for c in c_ids}
        sb.table('strategy_rules_v2').update({'condition_ids': c_ids, 'condition_weights': c_weights}).eq('id', rule['id']).execute()
        print("Updated Aa23 with DIP Sniper logic")
        
    # 4. Update AaHot
    res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'AaHot').execute()
    if res.data:
        rule = res.data[0]
        c_ids = list(set(rule['condition_ids'] + [75, 2]))
        w = round(1.0 / len(c_ids), 3)
        c_weights = {str(c): w for c in c_ids}
        sb.table('strategy_rules_v2').update({'condition_ids': c_ids, 'condition_weights': c_weights}).eq('id', rule['id']).execute()
        print("Updated AaHot with DIP Sniper logic")

if __name__ == "__main__":
    asyncio.run(update_dip_rules())
