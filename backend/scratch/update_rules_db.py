import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')
load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

async def main():
    print("=== STARTING DATABASE UPDATE ===")
    
    # 1. Insert variables if not exist
    variables_to_insert = [
        {
            "id": 113,
            "name": "Fresh Cross Long",
            "source_field": "fresh_cross_long",
            "description": "Indica si hubo cruce alcista reciente de EMA3/EMA9 o aceleracion alcista",
            "category": "indicators",
            "enabled": True
        },
        {
            "id": 114,
            "name": "Fresh Cross Short",
            "source_field": "fresh_cross_short",
            "description": "Indica si hubo cruce bajista reciente de EMA3/EMA9 o aceleracion bajista",
            "category": "indicators",
            "enabled": True
        }
    ]
    
    for var in variables_to_insert:
        existing = sb.table('strategy_variables').select('id').eq('id', var['id']).execute()
        if not existing.data:
            print(f"Inserting variable: {var['name']} (ID: {var['id']})")
            sb.table('strategy_variables').insert(var).execute()
        else:
            print(f"Variable {var['name']} (ID: {var['id']}) already exists, updating...")
            sb.table('strategy_variables').update(var).eq('id', var['id']).execute()

    # 2. Insert conditions if not exist
    conditions_to_insert = [
        {
            "id": 228,
            "name": "Cruce EMA3 > EMA9 (Fresh Cross Long)",
            "variable_id": 113,
            "operator": "==",
            "value_type": "literal",
            "value_literal": "1",
            "enabled": True,
            "description": "Crossover reciente alcista o aceleracion EMA3 sobre EMA9"
        },
        {
            "id": 229,
            "name": "Cruce EMA3 < EMA9 (Fresh Cross Short)",
            "variable_id": 114,
            "operator": "==",
            "value_type": "literal",
            "value_literal": "1",
            "enabled": True,
            "description": "Crossover reciente bajista o aceleracion EMA3 bajo EMA9"
        }
    ]
    
    for cond in conditions_to_insert:
        existing = sb.table('strategy_conditions').select('id').eq('id', cond['id']).execute()
        if not existing.data:
            print(f"Inserting condition: {cond['name']} (ID: {cond['id']})")
            sb.table('strategy_conditions').insert(cond).execute()
        else:
            print(f"Condition {cond['name']} (ID: {cond['id']}) already exists, updating...")
            sb.table('strategy_conditions').update(cond).eq('id', cond['id']).execute()

    # 3. Update AaHot rule
    print("Updating AaHot rule condition IDs to use 228...")
    sb.table('strategy_rules_v2').update({
        "condition_ids": [228],
        "condition_weights": {"228": 1.0}
    }).eq('rule_code', 'AaHot').execute()

    # 4. Update BbHot rule
    print("Updating BbHot rule condition IDs to use 229...")
    sb.table('strategy_rules_v2').update({
        "condition_ids": [229],
        "condition_weights": {"229": 1.0}
    }).eq('rule_code', 'BbHot').execute()

    # 5. Update Bb21 rule
    print("Updating Bb21 rule to remove contradictory conditions 221 and 222...")
    sb.table('strategy_rules_v2').update({
        "condition_ids": [37, 12, 47, 214, 215, 218, 226],
        "condition_weights": {
            "12": 0.2, 
            "37": 0.2, 
            "47": 0.2, 
            "214": 0.3, 
            "215": 0.1, 
            "218": 0.2, 
            "226": 0.2
        }
    }).eq('rule_code', 'Bb21').execute()

    print("=== DATABASE UPDATE COMPLETED ===")

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
