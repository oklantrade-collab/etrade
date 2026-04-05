import asyncio
from app.core.supabase_client import get_supabase

async def simple_update():
    sb = get_supabase()
    
    # 1. Check Vars
    vars_res = sb.table('strategy_variables').select('*').in_('source_field', ['is_4h_green', 'is_4h_red', 'ai_opportune_buy', 'ai_opportune_sell']).execute()
    v_map = {v['source_field']: v['id'] for v in vars_res.data}
    print(f"Vars Found: {v_map}")
    
    if not v_map:
        print("Wait, no variables found by source_field! Let's check IDs 4, 5, 6, 7.")
        vars_res = sb.table('strategy_variables').select('*').in_('id', [4, 5, 6, 7]).execute()
        print(f"Vars at IDs 4,5,6,7: {vars_res.data}")
    
    # 2. Check Conditions
    cond_names = ['No 4h Red Candle', 'No 4h Green Candle', 'AI Opportune Buy', 'AI Opportune Sell']
    conds_res = sb.table('strategy_conditions').select('*').in_('name', cond_names).execute()
    c_map = {c['name']: c['id'] for c in conds_res.data}
    print(f"Conds Found: {c_map}")
    
    # 3. Update Rule Dd61_15m explicitly if maps are filled
    if 'No 4h Red Candle' in c_map and 'AI Opportune Buy' in c_map:
        sb.table('strategy_rules_v2').update({
            'condition_ids': [58, 59, c_map['No 4h Red Candle'], c_map['AI Opportune Buy']],
            'condition_weights': {
                '58': 0.50, # Basis 15m
                str(c_map['No 4h Red Candle']): 0.30, # 4h State
                str(c_map['AI Opportune Buy']): 0.15, # Gemini
                '59': 0.05 # Lower 6
            }
        }).eq('rule_code', 'Dd61_15m').execute()
        print("Dd61_15m Updated!")

    if 'No 4h Green Candle' in c_map and 'AI Opportune Sell' in c_map:
        sb.table('strategy_rules_v2').update({
            'condition_ids': [58, 60, c_map['No 4h Green Candle'], c_map['AI Opportune Sell']],
            'condition_weights': {
                '58': 0.50, # Basis 15m
                str(c_map['No 4h Green Candle']): 0.30, # 4h State
                str(c_map['AI Opportune Sell']): 0.15, # Gemini
                '60': 0.05 # Upper 6
            }
        }).eq('rule_code', 'Dd51_15m').execute()
        print("Dd51_15m Updated!")

if __name__ == "__main__":
    asyncio.run(simple_update())
