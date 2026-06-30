import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

def update_bb30_db():
    print("--- Adding Strategy Variables ---")
    vars_data = [
        {"name": "ema20_below_ema50_15m", "source_field": "ema20_below_ema50_15m", "category": "technical", "enabled": True},
        {"name": "high_above_ema20_5m", "source_field": "high_above_ema20_5m", "category": "technical", "enabled": True},
        {"name": "bb_upper_descending_15m", "source_field": "bb_upper_descending_15m", "category": "technical", "enabled": True}
    ]
    
    var_ids = {}
    for v in vars_data:
        existing = sb.table('strategy_variables').select('id').eq('name', v['name']).execute()
        if existing.data:
            v['id'] = existing.data[0]['id']
        res = sb.table('strategy_variables').upsert(v).execute()
        var_ids[v['name']] = res.data[0]['id']
        print(f"Variable {v['name']} upserted with ID {res.data[0]['id']}.")

    print("\n--- Adding Strategy Conditions ---")
    conds = [
        {
            "name": "EMA20 < EMA50 (15m)",
            "variable_id": var_ids["ema20_below_ema50_15m"], 
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "name": "HIGH > EMA20 (5m)",
            "variable_id": var_ids["high_above_ema20_5m"], 
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "name": "BB Upper Descending (15m)",
            "variable_id": var_ids["bb_upper_descending_15m"], 
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        }
    ]
    
    cond_ids = {}
    for cond in conds:
        existing_cond = sb.table('strategy_conditions').select('id').eq('name', cond['name']).execute()
        if existing_cond.data:
            cond['id'] = existing_cond.data[0]['id']
        res_cond = sb.table('strategy_conditions').upsert(cond).execute()
        cond_ids[cond['name']] = res_cond.data[0]['id']
        print(f"Condition '{cond['name']}' upserted with ID {res_cond.data[0]['id']}.")

    print("\n--- Updating Rule Bb30 ---")
    rule_id_query = sb.table('strategy_rules_v2').select('id').eq('rule_code', 'Bb30').execute()
    if not rule_id_query.data:
        print("Rule Bb30 not found!")
        return
    rule_id = rule_id_query.data[0]['id']
    
    id_ema20_50 = cond_ids["EMA20 < EMA50 (15m)"]
    id_high = cond_ids["HIGH > EMA20 (5m)"]
    id_bb_up = cond_ids["BB Upper Descending (15m)"]
    
    # Existing IDs
    # 9907: EMA9 < EMA20 5m
    # 9911: EMA20 ángulo negativo 5m
    
    condition_ids_list = [id_ema20_50, id_high, id_bb_up, 9907, 9911]
    
    rule_data = {
        "notes": "Estrategia bajista (SIPV/5m): 15m EMA20<EMA50 (30%), 5m HIGH>EMA20 (20%), 15m BB Upper Desc (30%), 5m EMA9<EMA20 (10%), 5m EMA20 ang neg (10%).",
        "condition_ids": condition_ids_list,
        "condition_weights": {
            str(id_ema20_50): 0.30,
            str(id_high): 0.20,
            str(id_bb_up): 0.30,
            "9907": 0.10,
            "9911": 0.10
        },
        "min_score": 0.80,
        "applicable_cycles": ["15m", "5m"]
    }
    sb.table('strategy_rules_v2').update(rule_data).eq('id', rule_id).execute()
    print("Rule Bb30 updated.")

if __name__ == "__main__":
    update_bb30_db()
