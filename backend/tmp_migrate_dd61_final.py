import asyncio
from app.core.supabase_client import get_supabase

async def migrate_dd61_dd51():
    sb = get_supabase()
    
    # 1. Add Variables
    v_defs = [
        {'name': '4h Candle is Green', 'source_field': 'is_4h_green', 'data_type': 'boolean', 'description': '4h close > open', 'category': 'technical'},
        {'name': '4h Candle is Red', 'source_field': 'is_4h_red', 'data_type': 'boolean', 'description': '4h close < open', 'category': 'technical'},
        {'name': 'Gemini Opportune Buy', 'source_field': 'ai_opportune_buy', 'data_type': 'boolean', 'description': 'AI says it is a good buy time', 'category': 'sentiment'},
        {'name': 'Gemini Opportune Sell', 'source_field': 'ai_opportune_sell', 'data_type': 'boolean', 'description': 'AI says it is a good sell time', 'category': 'sentiment'},
    ]
    
    var_map = {}
    for v in v_defs:
        # Check by source_field
        res = sb.table('strategy_variables').select('id').eq('source_field', v['source_field']).execute()
        if res.data:
            var_map[v['source_field']] = res.data[0]['id']
            print(f"Found existing variable {v['source_field']}: {res.data[0]['id']}")
        else:
            ins = sb.table('strategy_variables').insert({**v, 'enabled': True}).execute()
            var_map[v['source_field']] = ins.data[0]['id']
            print(f"Inserted variable {v['source_field']}: {ins.data[0]['id']}")

    # 2. Add Conditions
    c_defs = [
        {'name': '4h Green Candle', 'variable_id': var_map['is_4h_green'], 'operator': '==', 'value_type': 'literal', 'value_literal': '1'},
        {'name': '4h Red Candle', 'variable_id': var_map['is_4h_red'], 'operator': '==', 'value_type': 'literal', 'value_literal': '1'},
        {'name': 'AI Opportune Buy', 'variable_id': var_map['ai_opportune_buy'], 'operator': '==', 'value_type': 'literal', 'value_literal': '1'},
        {'name': 'AI Opportune Sell', 'variable_id': var_map['ai_opportune_sell'], 'operator': '==', 'value_type': 'literal', 'value_literal': '1'},
        {'name': 'No 4h Red Candle', 'variable_id': var_map['is_4h_red'], 'operator': '==', 'value_type': 'literal', 'value_literal': '0'},
        {'name': 'No 4h Green Candle', 'variable_id': var_map['is_4h_green'], 'operator': '==', 'value_type': 'literal', 'value_literal': '0'},
    ]
    
    cond_map = {}
    for c in c_defs:
        res = sb.table('strategy_conditions').select('id').eq('name', c['name']).execute()
        if res.data:
            cond_map[c['name']] = res.data[0]['id']
            print(f"Found existing condition {c['name']}: {res.data[0]['id']}")
        else:
            ins = sb.table('strategy_conditions').insert({**c, 'enabled': True}).execute()
            cond_map[c['name']] = ins.data[0]['id']
            print(f"Inserted condition {c['name']}: {ins.data[0]['id']}")

    # 3. Update Rules Dd61_15m
    # Weights for basis = 0.50 as requested
    dd61_conds = [58, 59, cond_map['No 4h Red Candle'], cond_map['AI Opportune Buy']]
    sb.table('strategy_rules_v2').update({
        'condition_ids': dd61_conds,
        'condition_weights': {
            '58': 0.50,
            str(cond_map['No 4h Red Candle']): 0.30,
            str(cond_map['AI Opportune Buy']): 0.15,
            '59': 0.05
        }
    }).eq('rule_code', 'Dd61_15m').execute()
    print("Updated Dd61_15m")

    # 4. Update Rules Dd51_15m
    dd51_conds = [58, 60, cond_map['No 4h Green Candle'], cond_map['AI Opportune Sell']]
    sb.table('strategy_rules_v2').update({
        'condition_ids': dd51_conds,
        'condition_weights': {
            '58': 0.50,
            str(cond_map['No 4h Green Candle']): 0.30,
            str(cond_map['AI Opportune Sell']): 0.15,
            '60': 0.05
        }
    }).eq('rule_code', 'Dd51_15m').execute()
    print("Updated Dd51_15m")

if __name__ == "__main__":
    asyncio.run(migrate_dd61_dd51())
