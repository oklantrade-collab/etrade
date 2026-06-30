import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

def update_db():
    # 1. Ensure variable exists
    var_code = 'bb_lower_descending_15m'
    var_name = 'bb_lower_descending_15m'
    
    res_var = sb.table('strategy_variables').select('*').eq('name', var_name).execute()
    if not res_var.data:
        # Get max id
        r1 = sb.table('strategy_variables').select('id').order('id', desc=True).limit(1).execute()
        max_id = r1.data[0]['id'] if r1.data else 0
        new_var_id = max_id + 1
        
        new_var = {
            'id': new_var_id,
            'name': var_name,
            'description': 'Bollinger Lower Band in 15m is descending (last 3 candles)',
            'data_type': 'boolean',
            'category': 'indicator',
            'enabled': True
        }
        sb.table('strategy_variables').insert(new_var).execute()
        var_id = new_var_id
        print(f"Created variable {var_name} with ID {var_id}")
    else:
        var_id = res_var.data[0]['id']
        print(f"Variable {var_name} already exists with ID {var_id}")

    # 2. Ensure condition exists
    cond_name = 'BB Lower Descending 15m'
    res_cond = sb.table('strategy_conditions').select('*').eq('variable_id', var_id).eq('operator', '==').eq('value_literal', 1).execute()
    if not res_cond.data:
        r2 = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
        max_cond_id = r2.data[0]['id'] if r2.data else 0
        new_cond_id = max_cond_id + 1
        
        new_cond = {
            'id': new_cond_id,
            'name': cond_name,
            'variable_id': var_id,
            'operator': '==',
            'value_type': 'literal',
            'value_literal': 1,
            'timeframe': '15m',
            'description': 'Banda Inferior de Bollinger en descenso',
            'enabled': True
        }
        sb.table('strategy_conditions').insert(new_cond).execute()
        cond_id = new_cond_id
        print(f"Created condition '{cond_name}' with ID {cond_id}")
    else:
        cond_id = res_cond.data[0]['id']
        print(f"Condition '{cond_name}' already exists with ID {cond_id}")

    # 3. Update Bb30 Rule
    res_rule = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Bb30').execute()
    if res_rule.data:
        rule = res_rule.data[0]
        cond_ids = rule['condition_ids']
        if cond_id not in cond_ids:
            cond_ids.append(cond_id)
            
            # Need to update weights to include new condition
            weights = rule.get('condition_weights', {})
            # Redistribute weight slightly to give the new condition some weight (e.g. 0.15)
            # Just assigning 0.15 for now.
            weights[str(cond_id)] = 0.15
            
            sb.table('strategy_rules_v2').update({
                'condition_ids': cond_ids,
                'condition_weights': weights
            }).eq('id', rule['id']).execute()
            print(f"Updated Bb30 Rule (ID {rule['id']}) with condition {cond_id}")
        else:
            print(f"Bb30 Rule already has condition {cond_id}")
    else:
        print("Bb30 rule not found!")

if __name__ == '__main__':
    update_db()
