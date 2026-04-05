import asyncio
from app.core.supabase_client import get_supabase

async def manual_fix():
    sb = get_supabase()
    
    # Existing IDs for weights
    # 58: Mercado Lateral (Range)
    # 59: Precio en zona extrema LOWER_6
    # 60: Precio en zona extrema UPPER_6
    # 63: Inicio del SARS positivo (15m)
    # 64: Precio < BASIS
    # 66: Inicio del SARS negativo (15m)
    # 68: Precio > BASIS

    # 1. Provide High IDs for new variables and conditions to avoid sequence conflict
    # Variables (Source Fields must match StrategyEngine.build_context)
    # IDs confirmed free: 100-200
    vars_to_add = [
        {'id': 101, 'name': '4h Candle is Green', 'source_field': 'is_4h_green', 'data_type': 'boolean', 'category': 'technical'},
        {'id': 102, 'name': '4h Candle is Red', 'source_field': 'is_4h_red', 'data_type': 'boolean', 'category': 'technical'},
        {'id': 103, 'name': 'Gemini Opportune Buy', 'source_field': 'ai_opportune_buy', 'data_type': 'boolean', 'category': 'sentiment'},
        {'id': 104, 'name': 'Gemini Opportune Sell', 'source_field': 'ai_opportune_sell', 'data_type': 'boolean', 'category': 'sentiment'}
    ]
    
    for v in vars_to_add:
        try:
            sb.table('strategy_variables').upsert({**v, 'enabled': True}).execute()
            print(f"Added Var {v['id']}")
        except Exception as e:
            print(f"Var {v['id']} exists or err: {e}")

    # Conditions (IDs confirmed free: 200-300)
    conds_to_add = [
        {'id': 201, 'name': 'No 4h Red Candle (Long)', 'variable_id': 102, 'operator': '==', 'value_type': 'literal', 'value_literal': '0'},
        {'id': 202, 'name': 'No 4h Green Candle (Short)', 'variable_id': 101, 'operator': '==', 'value_type': 'literal', 'value_literal': '0'},
        {'id': 203, 'name': 'AI Opportune Buy', 'variable_id': 103, 'operator': '==', 'value_type': 'literal', 'value_literal': '1'},
        {'id': 204, 'name': 'AI Opportune Sell', 'variable_id': 104, 'operator': '==', 'value_type': 'literal', 'value_literal': '1'}
    ]
    
    for c in conds_to_add:
        try:
            sb.table('strategy_conditions').upsert({**c, 'enabled': True}).execute()
            print(f"Added Cond {c['id']}")
        except Exception as e:
            print(f"Cond {c['id']} exists or err: {e}")

    # 2. Update Weights and Conditions
    # Weights for Dd61_15m (ID 2)
    new_ids_61 = [58, 59, 201, 203] # Basis, L6, No-Red-4h, AI-Buy
    new_weights_61 = {
        '58': 0.50, # Determinant Basis
        '59': 0.10, # Zone 6
        '201': 0.25, # 4h Logic
        '203': 0.15  # AI Logic
    }
    sb.table('strategy_rules_v2').update({
        'condition_ids': new_ids_61,
        'condition_weights': new_weights_61,
        'min_score': 0.75
    }).eq('rule_code', 'Dd61_15m').execute()
    print("Dd61 Updated")

    # Weights for Dd51_15m (ID 4)
    new_ids_51 = [58, 60, 202, 204] # Basis, U6, No-Green-4h, AI-Sell
    new_weights_51 = {
        '58': 0.50,
        '60': 0.10,
        '202': 0.25,
        '204': 0.15
    }
    sb.table('strategy_rules_v2').update({
        'condition_ids': new_ids_51,
        'condition_weights': new_weights_51,
        'min_score': 0.75
    }).eq('rule_code', 'Dd51_15m').execute()
    print("Dd51 Updated")

if __name__ == "__main__":
    asyncio.run(manual_fix())
