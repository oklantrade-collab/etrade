import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

def update_aa41_db():
    print("--- Adding Strategy Variables ---")
    vars_data = [
        {
            "name": "bb_lower_ascending_2c_15m",
            "source_field": "bb_lower_ascending_2c_15m",
            "category": "technical",
            "enabled": True
        },
        {
            "name": "prev_low_touch_lower56_15m",
            "source_field": "prev_low_touch_lower56_15m",
            "category": "technical",
            "enabled": True
        }
    ]
    for v in vars_data:
        existing = sb.table('strategy_variables').select('*').eq('name', v['name']).execute()
        if existing.data:
            v['id'] = existing.data[0]['id']
        res = sb.table('strategy_variables').upsert(v).execute()
        print(f"Variable {v['name']} upserted with ID {res.data[0]['id']}.")

    var_bb = sb.table('strategy_variables').select('id').eq('name', 'bb_lower_ascending_2c_15m').execute().data[0]['id']
    var_low = sb.table('strategy_variables').select('id').eq('name', 'prev_low_touch_lower56_15m').execute().data[0]['id']

    print("\n--- Adding Strategy Conditions ---")
    conds = [
        {
            "name": "Banda Inferior ascendente (2 velas) (15m)",
            "variable_id": var_bb, 
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "name": "Vela anterior Low <= Lower5/6 (15m)",
            "variable_id": var_low, 
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

    print("\n--- Updating Rule Aa41 ---")
    rule_id_query = sb.table('strategy_rules_v2').select('id').eq('rule_code', 'Aa41').execute()
    if not rule_id_query.data:
        print("Rule Aa41 not found!")
        return
    rule_id = rule_id_query.data[0]['id']
    
    # 54: Range o Basis UP (OR)
    # 64: Precio < BASIS
    
    id_bb = cond_ids["Banda Inferior ascendente (2 velas) (15m)"]
    id_low = cond_ids["Vela anterior Low <= Lower5/6 (15m)"]
    
    condition_ids = [id_bb, id_low, 54, 64]
    
    rule_data = {
        "id": rule_id,
        "rule_code": "Aa41",
        "name": "ANTIGRAVITY CANDLE BUY (4H/1D)",
        "notes": "Estrategia alcista (SIPV): 15m BB Lower ascendente 2velas (30%), 15m PrevLow <= L5/L6 (30%), 15m Range/Basis UP (20%), Precio < Basis (20%).",
        "direction": "long",
        "strategy_type": "scalping",
        "cycle": "15m", 
        "applicable_cycles": ["15m", "4h", "1d"],
        "condition_ids": condition_ids,
        "condition_weights": {
            str(id_bb): 0.30,
            str(id_low): 0.30,
            "54": 0.20,
            "64": 0.20
        },
        "condition_logic": "AND", # Keep as original
        "min_score": 0.80, 
        "priority": 10,
        "enabled": True,
        "confidence": 0.85
    }
    sb.table('strategy_rules_v2').upsert(rule_data).execute()
    print("Rule Aa41 updated.")

if __name__ == "__main__":
    update_aa41_db()
