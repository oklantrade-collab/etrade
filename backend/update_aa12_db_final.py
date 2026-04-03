import asyncio
from app.core.supabase_client import get_supabase

async def update_aa12_db_fixed():
    sb = get_supabase()
    
    print("--- Adding Strategy Variables ---")
    vars_data = [
        {
            "id": 57,
            "name": "is_range_or_rise_15m",
            "source_field": "is_range_or_rise_15m",
            "category": "combined",
            "enabled": True
        },
        {
            "id": 58,
            "name": "sar_or_pine_5m",
            "source_field": "sar_or_pine_5m",
            "category": "combined",
            "enabled": True
        }
    ]
    for v in vars_data:
        sb.table('strategy_variables').upsert(v).execute()
        print(f"Variable {v['name']} upserted.")

    print("\n--- Adding Strategy Conditions ---")
    conditions = [
        {
            "id": 69,
            "name": "Range o Basis UP (OR) (15m)",
            "variable_id": 57, 
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "id": 70,
            "name": "Precio toca lower_5 (5m)",
            "variable_id": 1, 
            "operator": "<=",
            "value_type": "variable",
            "value_variable": "lower_5",
            "enabled": True
        },
        {
            "id": 71,
            "name": "(Inicio SARS+ o Pine Buy) (5m)",
            "variable_id": 58,
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "id": 72,
            "name": "Precio toca lower_6 (5m)",
            "variable_id": 1, 
            "operator": "<=",
            "value_type": "variable",
            "value_variable": "lower_6",
            "enabled": True
        }
    ]
    for cond in conditions:
        sb.table('strategy_conditions').upsert(cond).execute()
        print(f"Condition '{cond['name']}' upserted.")

    print("\n--- Updating Rule Aa12 ---")
    rule_data = {
        "id": 1002, # Correct ID for Aa12
        "rule_code": "Aa12",
        "name": "LONG Aa12: MTF Multi-Factor Sealp",
        "notes": "Estrategia alcista (5m): 15m Range/Rise (40%), 5m lower_5 (20%), 5m SAR+/Pine Buy (20%), 5m lower_6 (20%). Score min 80%",
        "direction": "long",
        "strategy_type": "scalping",
        "cycle": "5m", 
        "applicable_cycles": ["5m"],
        "condition_ids": [69, 70, 71, 72],
        "condition_weights": {
            "69": 0.40,
            "70": 0.20,
            "71": 0.20,
            "72": 0.20
        },
        "condition_logic": "OR",
        "min_score": 0.80,
        "priority": 0,
        "enabled": True,
        "confidence": 0.80
    }
    sb.table('strategy_rules_v2').upsert(rule_data).execute()
    print("Rule Aa12 updated.")

if __name__ == "__main__":
    asyncio.run(update_aa12_db_fixed())
