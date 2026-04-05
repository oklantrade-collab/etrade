import asyncio
from app.core.supabase_client import get_supabase

async def final_strategy_correction():
    sb = get_supabase()
    
    # 1. Variables Definition
    v_defs = [
        {'name': '4h Candle is Green', 'source_field': 'is_4h_green', 'data_type': 'boolean', 'category': 'technical'},
        {'name': '4h Candle is Red', 'source_field': 'is_4h_red', 'data_type': 'boolean', 'category': 'technical'},
        {'name': 'Gemini Opportune Buy', 'source_field': 'ai_opportune_buy', 'data_type': 'boolean', 'category': 'sentiment'},
        {'name': 'Gemini Opportune Sell', 'source_field': 'ai_opportune_sell', 'data_type': 'boolean', 'category': 'sentiment'}
    ]
    
    v_ids = {}
    for v in v_defs:
        res = sb.table('strategy_variables').select('id').eq('source_field', v['source_field']).execute()
        if res.data:
            v_ids[v['source_field']] = res.data[0]['id']
        else:
            ins = sb.table('strategy_variables').insert({**v, 'enabled': True}).execute()
            v_ids[v['source_field']] = ins.data[0]['id']
            print(f"Added Var: {v['source_field']} with ID {v_ids[v['source_field']]}")

    # 2. Conditions Definition
    c_defs = [
        {'name': 'No 4h Red Candle (Long)', 'variable_id': v_ids['is_4h_red'], 'operator': '==', 'value_literal': '0'},
        {'name': 'No 4h Green Candle (Short)', 'variable_id': v_ids['is_4h_green'], 'operator': '==', 'value_literal': '0'},
        {'name': 'AI Opportune Buy', 'variable_id': v_ids['ai_opportune_buy'], 'operator': '==', 'value_literal': '1'},
        {'name': 'AI Opportune Sell', 'variable_id': v_ids['ai_opportune_sell'], 'operator': '==', 'value_literal': '1'}
    ]
    
    c_ids = {}
    for c in c_defs:
        res = sb.table('strategy_conditions').select('id').eq('name', c['name']).execute()
        if res.data:
            c_ids[c['name']] = res.data[0]['id']
        else:
            ins = sb.table('strategy_conditions').insert({**c, 'enabled': True, 'value_type': 'literal'}).execute()
            c_ids[c['name']] = ins.data[0]['id']
            print(f"Added Cond: {c['name']} with ID {c_ids[c['name']]}")

    # 3. Update Rule Dd61_15m (LONG)
    # Basis (58) = 0.50
    # No Red 4h = 0.25
    # AI Opportune = 0.15
    # Extreme Zone LOWER_6 (59) = 0.10
    conds_61 = [58, 59, c_ids['No 4h Red Candle (Long)'], c_ids['AI Opportune Buy']]
    weights_61 = {
        '58': 0.50, # Determinant Basis
        '59': 0.10, # Zone 6
        str(c_ids['No 4h Red Candle (Long)']): 0.25,
        str(c_ids['AI Opportune Buy']): 0.15
    }
    sb.table('strategy_rules_v2').update({
        'condition_ids': conds_61,
        'condition_weights': weights_61,
        'min_score': 0.75
    }).eq('rule_code', 'Dd61_15m').execute()
    print("Dd61_15m Updated")

    # 4. Update Rule Dd51_15m (SHORT)
    # Basis (58) = 0.50
    # No Green 4h = 0.25
    # AI Opportune = 0.15
    # Extreme Zone UPPER_6 (60) = 0.10
    conds_51 = [58, 60, c_ids['No 4h Green Candle (Short)'], c_ids['AI Opportune Sell']]
    weights_51 = {
        '58': 0.50, # Determinant Basis
        '60': 0.10, # Zone 6
        str(c_ids['No 4h Green Candle (Short)']): 0.25,
        str(c_ids['AI Opportune Sell']): 0.15
    }
    sb.table('strategy_rules_v2').update({
        'condition_ids': conds_51,
        'condition_weights': weights_51,
        'min_score': 0.75
    }).eq('rule_code', 'Dd51_15m').execute()
    print("Dd51_15m Updated")

if __name__ == "__main__":
    asyncio.run(final_strategy_correction())
