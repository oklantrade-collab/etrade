import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

def update_aa12_db():
    print("--- Adding Strategy Variables ---")
    vars_data = [
        {
            "name": "ema9_above_ema20_15m",
            "source_field": "ema9_above_ema20_15m",
            "category": "technical",
            "enabled": True
        },
        {
            "name": "is_range_or_rise_15m_new",
            "source_field": "is_range_or_rise_15m",
            "category": "combined",
            "enabled": True
        }
    ]
    for v in vars_data:
        existing = sb.table('strategy_variables').select('*').eq('name', v['name']).execute()
        if existing.data:
            v['id'] = existing.data[0]['id']
        res = sb.table('strategy_variables').upsert(v).execute()
        print(f"Variable {v['name']} upserted with ID {res.data[0]['id']}.")

    var_ema9 = sb.table('strategy_variables').select('id').eq('name', 'ema9_above_ema20_15m').execute().data[0]['id']
    var_range = sb.table('strategy_variables').select('id').eq('name', 'is_range_or_rise_15m_new').execute().data[0]['id']

    print("\n--- Adding Strategy Conditions ---")
    # Using specific names so they stand out
    conds = [
        {
            "name": "EMA9 > EMA20 (15m) (Aa12)",
            "variable_id": var_ema9, 
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "name": "Range o Basis UP (OR) (15m) (Aa12)",
            "variable_id": var_range, 
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

    print("\n--- Updating Rule Aa12 ---")
    rule_id_query = sb.table('strategy_rules_v2').select('id').eq('rule_code', 'Aa12').execute()
    if not rule_id_query.data:
        print("Rule Aa12 not found!")
        return
    rule_id = rule_id_query.data[0]['id']
    
    # Existing IDs from previous analysis:
    # 20: Precio toca lower_5
    # 21: Precio toca lower_6
    
    id_ema9 = cond_ids["EMA9 > EMA20 (15m) (Aa12)"]
    id_range = cond_ids["Range o Basis UP (OR) (15m) (Aa12)"]
    
    condition_ids = [id_ema9, id_range, 20, 21]
    
    rule_data = {
        "id": rule_id,
        "rule_code": "Aa12",
        "name": "LONG Aa12: MTF Multi-Factor Sealp",
        "notes": "Estrategia alcista (5m): 15m EMA9>EMA20 (30%), 15m Range/Rise (30%), 5m lower_5 (20%), 5m lower_6 (20%). [MTF_OVERRIDE:0]",
        "direction": "long",
        "strategy_type": "scalping",
        "cycle": "5m", 
        "applicable_cycles": ["5m", "15m"],
        "condition_ids": condition_ids,
        "condition_weights": {
            str(id_ema9): 0.30,
            str(id_range): 0.30,
            "20": 0.20,
            "21": 0.20
        },
        "condition_logic": "OR",
        "min_score": 0.65, 
        "priority": 0,
        "enabled": True,
        "confidence": 0.8
    }
    sb.table('strategy_rules_v2').upsert(rule_data).execute()
    print("Rule Aa12 updated.")

if __name__ == "__main__":
    update_aa12_db()
