import asyncio
from app.core.supabase_client import get_supabase

async def final_db_update():
    sb = get_supabase()
    
    # Get all variables to identify IDs correctly
    vars_res = sb.table('strategy_variables').select('*').execute()
    v_map = {v['source_field']: v['id'] for v in vars_res.data}
    
    # Map specifically what we need (source_field -> ID)
    # If some are missing (like AI ones), we add them carefully
    needed = ['is_4h_green', 'is_4h_red', 'ai_opportune_buy', 'ai_opportune_sell']
    
    for nf in needed:
        if nf not in v_map:
            # Try to insert and catch error
            try:
                # Add with minimal fields
                name = nf.replace('_', ' ').capitalize()
                cat = 'technical' if '4h' in nf else 'sentiment'
                res = sb.table('strategy_variables').insert({
                    'name': name, 'source_field': nf, 'data_type': 'boolean', 'category': cat, 'enabled': True
                }).execute()
                v_map[nf] = res.data[0]['id']
                print(f"Added new variable {nf}: {res.data[0]['id']}")
            except Exception as e:
                # Refresh v_map
                v_map = {v['source_field']: v['id'] for v in sb.table('strategy_variables').select('*').execute().data}
                print(f"Skipped {nf} as it exists or error: {str(e)[:50]}")

    # Same for conditions
    conds_needed = [
        ('No 4h Red Candle', v_map.get('is_4h_red'), '==', '0'),
        ('No 4h Green Candle', v_map.get('is_4h_green'), '==', '0'),
        ('AI Opportune Buy', v_map.get('ai_opportune_buy'), '==', '1'),
        ('AI Opportune Sell', v_map.get('ai_opportune_sell'), '==', '1')
    ]
    
    c_map = {}
    for name, vid, op, val in conds_needed:
        if not vid: continue
        res = sb.table('strategy_conditions').select('id').eq('name', name).execute()
        if res.data:
            c_map[name] = res.data[0]['id']
        else:
            try:
                res = sb.table('strategy_conditions').insert({
                    'name': name, 'variable_id': vid, 'operator': op, 'value_type': 'literal', 'value_literal': val, 'enabled': True
                }).execute()
                c_map[name] = res.data[0]['id']
            except: 
                c_map[name] = sb.table('strategy_conditions').select('id').eq('name', name).maybe_single().execute().data['id']

    # Final Update for Dd61_15m
    if 'No 4h Red Candle' in c_map and 'AI Opportune Buy' in c_map:
        conds = [58, 59, c_map['No 4h Red Candle'], c_map['AI Opportune Buy']]
        sb.table('strategy_rules_v2').update({
            'condition_ids': conds,
            'condition_weights': {
                '58': 0.50, # Basis (requested weight)
                str(c_map['No 4h Red Candle']): 0.30,
                str(c_map['AI Opportune Buy']): 0.15,
                '59': 0.05 # Lower 6 zone
            },
            'min_score': 0.75 # Keep as was
        }).eq('rule_code', 'Dd61_15m').execute()
        print("Dd61 updated.")

    # Final Update for Dd51_15m
    if 'No 4h Green Candle' in c_map and 'AI Opportune Sell' in c_map:
        conds = [58, 60, c_map['No 4h Green Candle'], c_map['AI Opportune Sell']]
        sb.table('strategy_rules_v2').update({
            'condition_ids': conds,
            'condition_weights': {
                '58': 0.50, # Basis (requested weight)
                str(c_map['No 4h Green Candle']): 0.30,
                str(c_map['AI Opportune Sell']): 0.15,
                '60': 0.05
            },
            'min_score': 0.75
        }).eq('rule_code', 'Dd51_15m').execute()
        print("Dd51 updated.")

if __name__ == "__main__":
    asyncio.run(final_db_update())
