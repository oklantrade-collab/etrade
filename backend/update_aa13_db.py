import asyncio
from app.core.supabase_client import get_supabase

async def update_db_for_aa13():
    sb = get_supabase()
    
    print("--- Adding Strategy Variable: is_range_or_rise_4h ---")
    var_data = {
        "id": 55,
        "name": "is_range_or_rise_4h",
        "description": "Mercado Lateral o Basis Subiendo en 4 horas",
        "source_field": "is_range_or_rise_4h",
        "category": "combined",
        "enabled": True
    }
    try:
        sb.table('strategy_variables').upsert(var_data).execute()
        print("Variable is_range_or_rise_4h upserted.")
    except Exception as e:
        print(f"Error upserting variable: {e}")

    print("\n--- Adding Strategy Conditions ---")
    conditions = [
        {
            "id": 63,
            "name": "Inicio del SARS positivo (15m)",
            "variable_id": 33, # sar_ini_high_15m
            "operator": "==",
            "value_type": "literal",
            "value_literal": "True",
            "enabled": True
        },
        {
            "id": 64,
            "name": "Precio < BASIS",
            "variable_id": 1, # price
            "operator": "<",
            "value_type": "variable",
            "value_variable": "basis",
            "enabled": True
        },
        {
            "id": 65,
            "name": "Range o Basis UP (OR) (4h)",
            "variable_id": 55, # is_range_or_rise_4h
            "operator": "==",
            "value_type": "literal",
            "value_literal": "True",
            "enabled": True
        }
    ]
    
    for cond in conditions:
        try:
            sb.table('strategy_conditions').upsert(cond).execute()
            print(f"Condition '{cond['name']}' upserted.")
        except Exception as e:
            print(f"Error upserting condition {cond['name']}: {e}")

    print("\n--- Creating Rule Aa13 ---")
    # Rule: 15m scalp, Score 80%, weights 20% each.
    # Conditions:
    # 64: Close < BASIS (20%)
    # 54: Range o Basis UP (OR) (20%)
    # 36: PineScript Buy (B) (20%)
    # 63: Inicio del SARS positivo (20%)
    # 65: Range o Basis UP (OR) en 4horas (20%)
    
    rule_id = 2013 # Use a high ID range for new rules if needed, or check existing
    rule_code = "Aa13"
    
    rule_data = {
        "rule_code": rule_code,
        "name": "LONG Aa13: Bullish Buy Strategy",
        "description": "Estrategia alcista: Close < BASIS, Range/Rise 15m/4h, Pine Buy, SAR Inicio+",
        "direction": "long",
        "strategy_type": "scalping",
        "cycle": "15m",
        "applicable_cycles": ["15m"],
        "condition_ids": [64, 54, 36, 63, 65],
        "condition_weights": {
            "64": 0.20,
            "54": 0.20,
            "36": 0.20,
            "63": 0.20,
            "65": 0.20
        },
        "condition_logic": "OR", # Because we use weights and min_score, OR logic in StrategyEngine evaluates score >= min_score
        "min_score": 0.80,
        "priority": 5,
        "enabled": True
    }
    
    # Check if rule exists to use its ID or create new
    existing = sb.table('strategy_rules_v2').select('id').eq('rule_code', rule_code).execute()
    if existing.data:
        rule_data['id'] = existing.data[0]['id']
        print(f"Updating existing rule {rule_code} (ID: {rule_data['id']})")
    else:
        print(f"Creating new rule {rule_code}")

    try:
        sb.table('strategy_rules_v2').upsert(rule_data).execute()
        print(f"Rule {rule_code} upserted successfully.")
    except Exception as e:
        print(f"Error upserting rule {rule_code}: {e}")

if __name__ == "__main__":
    asyncio.run(update_db_for_aa13())
