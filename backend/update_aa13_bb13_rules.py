import asyncio
from app.core.supabase_client import get_supabase

async def migrate_aa13_bb13():
    sb = get_supabase()
    
    # 1. Add new variables
    print("--- Adding New Strategy Variables ---")
    variables = [
        {
            "id": 56,
            "name": "bb_lower_ascending_15m",
            "description": "Banda inferior BB asciende en velas actuales",
            "source_field": "bb_lower_ascending_15m",
            "category": "combined",
            "enabled": True
        },
        {
            "id": 57,
            "name": "bb_upper_descending_15m",
            "description": "Banda superior BB desciende en velas actuales",
            "source_field": "bb_upper_descending_15m",
            "category": "combined",
            "enabled": True
        },
        {
            "id": 58,
            "name": "high_above_ema20_15m",
            "description": "Precio máximo supera la EMA20",
            "source_field": "high_above_ema20_15m",
            "category": "combined",
            "enabled": True
        },
        {
            "id": 59,
            "name": "ema20_below_ema50_15m",
            "description": "EMA20 menor a EMA50 en 15m",
            "source_field": "ema20_below_ema50_15m",
            "category": "combined",
            "enabled": True
        },
        {
            "id": 60,
            "name": "ema9_below_ema20_15m",
            "description": "EMA9 menor a EMA20 en 15m",
            "source_field": "ema9_below_ema20_15m",
            "category": "combined",
            "enabled": True
        }
    ]
    for var in variables:
        try:
            sb.table('strategy_variables').upsert(var).execute()
            print(f"Variable '{var['name']}' upserted.")
        except Exception as e:
            print(f"Error upserting variable {var['name']}: {e}")

    # 2. Add new conditions
    print("\n--- Adding New Strategy Conditions ---")
    conditions = [
        {
            "id": 66,
            "name": "BB Lower Ascendiendo",
            "variable_id": 56,
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "id": 67,
            "name": "BB Upper Descendiendo",
            "variable_id": 57,
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "id": 68,
            "name": "HIGH toca EMA20",
            "variable_id": 58,
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "id": 69,
            "name": "EMA20 < EMA50",
            "variable_id": 59,
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        },
        {
            "id": 70,
            "name": "EMA9 < EMA20",
            "variable_id": 60,
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "enabled": True
        }
    ]
    for cond in conditions:
        try:
            sb.table('strategy_conditions').upsert(cond).execute()
            print(f"Condition '{cond['name']}' upserted.")
        except Exception as e:
            print(f"Error upserting condition {cond['name']}: {e}")

    # 3. Update Aa13
    print("\n--- Updating Rule Aa13 ---")
    rule_code_aa = "Aa13"
    existing_aa = sb.table('strategy_rules_v2').select('id, market_types').eq('rule_code', rule_code_aa).execute()
    
    aa_rule_data = {
        "rule_code": rule_code_aa,
        "name": "LONG Aa13: cazar suelo",
        "notes": "Estrategia alcista: Close < BASIS, Range/Rise, Pine Buy, SAR Inicio+, 4h Range/Rise, BB Lower Ascendiendo",
        "direction": "long",
        "strategy_type": "scalping",
        "cycle": "15m",
        "applicable_cycles": ["15m"],
        "condition_ids": [64, 54, 36, 63, 65, 66],
        "condition_weights": {
            "36": 0.166,
            "54": 0.166,
            "63": 0.166,
            "64": 0.166,
            "65": 0.166,
            "66": 0.166
        },
        "condition_logic": "OR",
        "min_score": 0.80, # Requires ~5 out of 6
        "priority": 5,
        "enabled": True,
        "confidence": 0.8
    }
    if existing_aa.data:
        aa_rule_data['id'] = existing_aa.data[0]['id']
        aa_rule_data['market_types'] = existing_aa.data[0].get('market_types')
        
    try:
        sb.table('strategy_rules_v2').upsert(aa_rule_data).execute()
        print(f"Rule {rule_code_aa} updated successfully.")
    except Exception as e:
        print(f"Error updating rule {rule_code_aa}: {e}")

    # 4. Create/Rebuild Bb13
    print("\n--- Creating Rule Bb13 ---")
    rule_code_bb = "Bb13"
    existing_bb = sb.table('strategy_rules_v2').select('id').eq('rule_code', rule_code_bb).execute()
    
    bb_rule_data = {
        "rule_code": rule_code_bb,
        "name": "SHORT Bb13: Bearish Pullback",
        "notes": "Estrategia bajista: EMA9 < 20, EMA20 < 50, Precio toca EMA20, BB Upper descendiendo",
        "direction": "short",
        "strategy_type": "scalping",
        "cycle": "15m",
        "applicable_cycles": ["15m"],
        "condition_ids": [70, 69, 68, 67],
        "condition_weights": {
            "67": 0.25,
            "68": 0.25,
            "69": 0.25,
            "70": 0.25
        },
        "condition_logic": "OR", 
        "min_score": 0.95, 
        "priority": 5,
        "enabled": True,
        "confidence": 0.9,
        "market_types": ["crypto_futures", "forex_futures"] 
    }
    if existing_bb.data:
        bb_rule_data['id'] = existing_bb.data[0]['id']
        
    try:
        sb.table('strategy_rules_v2').upsert(bb_rule_data).execute()
        print(f"Rule {rule_code_bb} upserted successfully.")
    except Exception as e:
        print(f"Error upserting rule {rule_code_bb}: {e}")

if __name__ == "__main__":
    asyncio.run(migrate_aa13_bb13())
