import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def apply():
    print("--- 1. UPSERT VARIABLE close_below_ema20_15m ---")
    var_data = {
        "name": "close_below_ema20_15m",
        "description": "Precio de cierre es menor a EMA20 en 15m",
        "source_field": "close_below_ema20_15m",
        "category": "technical",
        "enabled": True
    }
    # Check if exists
    res = sb.table('strategy_variables').select('id').eq('name', var_data['name']).execute()
    if res.data:
        var_data['id'] = res.data[0]['id']
    
    upsert_res = sb.table('strategy_variables').upsert(var_data).execute()
    var_id = upsert_res.data[0]['id']
    print(f"Variable ID: {var_id}")

    print("--- 2. UPSERT CONDITION ---")
    cond_data = {
        "name": "CLOSE < EMA20 (15m)",
        "variable_id": var_id,
        "operator": "==",
        "value_type": "literal",
        "value_literal": 1,
        "enabled": True
    }
    c_res = sb.table('strategy_conditions').select('id').eq('name', cond_data['name']).execute()
    if c_res.data:
        cond_data['id'] = c_res.data[0]['id']
        
    c_upsert = sb.table('strategy_conditions').upsert(cond_data).execute()
    cond_id = c_upsert.data[0]['id']
    print(f"Condition ID: {cond_id}")

    print("--- 3. ADD TO Bb13 ---")
    rule_res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Bb13').execute()
    if not rule_res.data:
        print("Rule Bb13 not found.")
        return
    
    rule = rule_res.data[0]
    cond_ids = rule.get('condition_ids', [])
    weights = rule.get('condition_weights', {})
    
    if cond_id not in cond_ids:
        cond_ids.append(cond_id)
        
    # Recalculate weights. We will evenly distribute or just append and re-normalize
    # The current weights sum to 1.0 in the screenshot.
    # We will just divide 1.0 by the number of conditions.
    new_weights = {}
    w = round(1.0 / len(cond_ids), 3)
    for cid in cond_ids:
        new_weights[str(cid)] = w
        
    # Ensure min score is high enough to require all conditions (e.g. 0.95 or 0.9)
    # The sum might be slightly less or more than 1.0 due to rounding, so 0.9 is safe
    update_data = {
        "condition_ids": cond_ids,
        "condition_weights": new_weights,
        "min_score": 0.9,
        "notes": rule.get('notes', '') + " + CLOSE < EMA20",
    }
    
    sb.table('strategy_rules_v2').update(update_data).eq('id', rule['id']).execute()
    print("Rule Bb13 successfully updated with the new close condition.")

if __name__ == '__main__':
    apply()
