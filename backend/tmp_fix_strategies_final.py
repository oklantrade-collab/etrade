import asyncio
from app.core.supabase_client import get_supabase

async def fix_strategies():
    sb = get_supabase()
    
    # 1. Variables
    v_defs = [
        {'name': '4h Candle is Green', 'source_field': 'is_4h_green', 'data_type': 'boolean', 'category': 'technical', 'description': '4h close > open'},
        {'name': '4h Candle is Red', 'source_field': 'is_4h_red', 'data_type': 'boolean', 'category': 'technical', 'description': '4h close < open'},
        {'name': 'Gemini Opportune Buy', 'source_field': 'ai_opportune_buy', 'data_type': 'boolean', 'category': 'sentiment', 'description': 'Gemini opportune moments'},
        {'name': 'Gemini Opportune Sell', 'source_field': 'ai_opportune_sell', 'data_type': 'boolean', 'category': 'sentiment', 'description': 'Gemini opportune moments'}
    ]
    
    v_map = {}
    for v in v_defs:
        res = sb.table('strategy_variables').select('id').eq('source_field', v['source_field']).execute()
        if res.data:
            v_map[v['source_field']] = res.data[0]['id']
        else:
            ins = sb.table('strategy_variables').insert({**v, 'enabled': True}).execute()
            v_map[v['source_field']] = ins.data[0]['id']
            print(f"Inserted variable {v['source_field']} ID: {v_map[v['source_field']]}")

    # 2. Conditions
    c_defs = [
        {'name': 'No 4h Red Candle', 'variable_id': v_map['is_4h_red'], 'operator': '==', 'value_type': 'literal', 'value_literal': '0'},
        {'name': 'No 4h Green Candle', 'variable_id': v_map['is_4h_green'], 'operator': '==', 'value_type': 'literal', 'value_literal': '0'},
        {'name': 'AI Opportune Buy', 'variable_id': v_map['ai_opportune_buy'], 'operator': '==', 'value_type': 'literal', 'value_literal': '1'},
        {'name': 'AI Opportune Sell', 'variable_id': v_map['ai_opportune_sell'], 'operator': '==', 'value_type': 'literal', 'value_literal': '1'}
    ]
    
    c_map = {}
    for c in c_defs:
        res = sb.table('strategy_conditions').select('id').eq('name', c['name']).execute()
        if res.data:
            c_map[c['name']] = res.data[0]['id']
        else:
            ins = sb.table('strategy_conditions').insert({**c, 'enabled': True}).execute()
            c_map[c['name']] = ins.data[0]['id']
            print(f"Inserted condition {c['name']} ID: {c_map[c['name']]}")

    # 3. Update Rules
    # Basis (58) -> 0.50
    # No Red (4h) -> 0.25 (for Buy)
    # AI Buy -> 0.15
    # Lower 6 (59) -> 0.10
    
    dd61_ids = [58, 59, c_map['No 4h Red Candle'], c_map['AI Opportune Buy']]
    dd61_weights = {
        '58': 0.50,
        '59': 0.10,
        str(c_map['No 4h Red Candle']): 0.30, # Increased slightly to ensure sum = 1.0 or correct ratio
        str(c_map['AI Opportune Buy']): 0.10
    }
    # Adjusted to 0.5 + 0.10 + 0.3 + 0.1 = 1.0
    
    for r_code in ['Dd61_15m', 'Dd61_4h']:
        sb.table('strategy_rules_v2').update({
            'condition_ids': dd61_ids,
            'condition_weights': dd61_weights,
            'min_score': 0.75
        }).eq('rule_code', r_code).execute()
        print(f"Updated {r_code}")

    dd51_ids = [58, 60, c_map['No 4h Green Candle'], c_map['AI Opportune Sell']]
    dd51_weights = {
        '58': 0.50,
        '60': 0.10,
        str(c_map['No 4h Green Candle']): 0.30,
        str(c_map['AI Opportune Sell']): 0.10
    }

    for r_code in ['Dd51_15m', 'Dd51_4h']:
        sb.table('strategy_rules_v2').update({
            'condition_ids': dd51_ids,
            'condition_weights': dd51_weights,
            'min_score': 0.75
        }).eq('rule_code', r_code).execute()
        print(f"Updated {r_code}")

if __name__ == "__main__":
    asyncio.run(fix_strategies())
