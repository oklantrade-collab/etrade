import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

def update_rsi_60():
    sb = get_supabase()
    
    # We know the condition ID is 9924 based on our previous script output
    # Let's verify it's the RSI > 65 one
    cond_res = sb.table('strategy_conditions').select('*').eq('id', 9924).execute()
    
    if cond_res.data and cond_res.data[0]['name'] == 'RSI > 65 5m':
        print("Found condition 9924. Updating to RSI > 60...")
        sb.table('strategy_conditions').update({
            'name': 'RSI > 60 5m',
            'description': 'RSI 5m por encima de 60 (Sobrecompra)',
            'value_literal': 60
        }).eq('id', 9924).execute()
        
        print("Condition 9924 updated to RSI > 60.")
    else:
        print("Condition 9924 not found or not RSI > 65 5m. Doing it safely...")
        # Create or find RSI > 60 5m
        res = sb.table('strategy_conditions').select('*').eq('name', 'RSI > 60 5m').execute()
        if res.data:
            rsi_cond_id = res.data[0]['id']
            print(f"Found existing RSI > 60 5m with ID {rsi_cond_id}")
        else:
            max_id_res = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
            rsi_cond_id = (max_id_res.data[0]['id'] + 1) if max_id_res.data else 1
            
            new_cond = {
                'id': rsi_cond_id,
                'name': 'RSI > 60 5m',
                'description': 'RSI 5m por encima de 60 (Sobrecompra)',
                'variable_id': 112,
                'operator': '>',
                'value_type': 'literal',
                'value_literal': 60,
                'timeframe': '5m',
                'enabled': True
            }
            sb.table('strategy_conditions').insert(new_cond).execute()
            print(f"Created RSI > 60 5m with ID {rsi_cond_id}")
            
        # Update Rule Bb52
        rule_res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Bb52').execute()
        if rule_res.data:
            rule = rule_res.data[0]
            cond_ids = rule['condition_ids']
            weights = rule['condition_weights']
            
            # Find the old RSI > 65 condition (if not 9924) and replace it
            old_rsi_res = sb.table('strategy_conditions').select('id').eq('name', 'RSI > 65 5m').execute()
            if old_rsi_res.data:
                old_id = old_rsi_res.data[0]['id']
                if old_id in cond_ids:
                    cond_ids.remove(old_id)
                    if str(old_id) in weights:
                        del weights[str(old_id)]
            
            if rsi_cond_id not in cond_ids:
                cond_ids.append(rsi_cond_id)
                weights[str(rsi_cond_id)] = 0.2
                
            sb.table('strategy_rules_v2').update({
                'condition_ids': cond_ids,
                'condition_weights': weights
            }).eq('rule_code', 'Bb52').execute()
            print("Updated Bb52 with new RSI condition.")
            
if __name__ == '__main__':
    update_rsi_60()
