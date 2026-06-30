import os
import json
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

def update_bb13():
    print("--- UPSERT VARIABLE ---")
    var_data = {"name": "ema50_below_ema200_15m", "source_field": "ema50_below_ema200_15m", "category": "technical", "enabled": True}
    res_var = sb.table('strategy_variables').select('id').eq('name', var_data['name']).execute()
    if res_var.data:
        var_data['id'] = res_var.data[0]['id']
    var_upsert = sb.table('strategy_variables').upsert(var_data).execute()
    var_id = var_upsert.data[0]['id']
    print(f"Variable ID: {var_id}")

    print("--- UPSERT CONDITION ---")
    cond_data = {
        "name": "EMA50 < EMA200 (15m)",
        "variable_id": var_id,
        "operator": "==",
        "value_type": "literal",
        "value_literal": 1,
        "enabled": True
    }
    res_cond = sb.table('strategy_conditions').select('id').eq('name', cond_data['name']).execute()
    if res_cond.data:
        cond_data['id'] = res_cond.data[0]['id']
    cond_upsert = sb.table('strategy_conditions').upsert(cond_data).execute()
    new_cond_id = cond_upsert.data[0]['id']
    print(f"New Condition ID: {new_cond_id}")

    print("--- UPDATE Bb13 ---")
    rule_res = sb.table('strategy_rules_v2').select('id', 'condition_ids').eq('rule_code', 'Bb13').execute()
    if not rule_res.data:
        print("Rule Bb13 not found.")
        return
    rule = rule_res.data[0]
    
    # We want to keep existing conditions but change weights to 20%, and add new one at 20%
    # Existing IDs for Bb13 from earlier: 67, 68, 69, 70
    old_ids = [67, 68, 69, 70]
    new_ids = old_ids + [new_cond_id]
    
    weights = {}
    for cid in new_ids:
        weights[str(cid)] = 0.20
        
    update_data = {
        "condition_ids": new_ids,
        "condition_weights": weights,
        "min_score": 1.0, # All must be met, so 5 * 0.20 = 1.0
        "notes": "Estrategia bajista (Pullback): EMA9<20, EMA20<50, EMA50<200, HIGH toca EMA20, BB Upper desc."
    }
    sb.table('strategy_rules_v2').update(update_data).eq('id', rule['id']).execute()
    print("Rule Bb13 successfully updated.")

if __name__ == '__main__':
    update_bb13()
