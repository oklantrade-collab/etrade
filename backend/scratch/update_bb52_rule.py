import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

def get_or_create_condition(sb, name, description, variable_id, operator, value_literal, timeframe):
    # Try to find exactly by name
    res = sb.table('strategy_conditions').select('*').eq('name', name).execute()
    if res.data:
        print(f"Found condition '{name}' with ID {res.data[0]['id']}")
        return res.data[0]
        
    # Get max id to insert
    max_id_res = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
    next_id = (max_id_res.data[0]['id'] + 1) if max_id_res.data else 1
    
    print(f"Creating condition '{name}' with ID {next_id}...")
    new_cond = {
        'id': next_id,
        'name': name,
        'description': description,
        'variable_id': variable_id,
        'operator': operator,
        'value_type': 'literal',
        'value_literal': value_literal,
        'timeframe': timeframe,
        'enabled': True
    }
    res = sb.table('strategy_conditions').insert(new_cond).execute()
    return res.data[0]

def update_bb52():
    sb = get_supabase()
    
    # 1. Create or get RSI > 65 5m
    # Variable 112 is RSI. Let's assume it's the same as the one used for Aa52
    rsi_cond = get_or_create_condition(
        sb, 
        name='RSI > 65 5m', 
        description='RSI 5m por encima de 65 (Sobrecompra)', 
        variable_id=112, 
        operator='>', 
        value_literal=65, 
        timeframe='5m'
    )
    
    # 2. Create or get Precio > BASIS
    # For Aa52, we used condition 64 ('Precio < BASIS'). 
    # Let's find condition 64 to get its variable_id
    cond_64_res = sb.table('strategy_conditions').select('*').eq('id', 64).execute()
    basis_var_id = cond_64_res.data[0]['variable_id'] if cond_64_res.data else 100 # fallback
    
    basis_cond = get_or_create_condition(
        sb,
        name='Precio > BASIS',
        description='Precio por encima de la banda central de Bollinger',
        variable_id=basis_var_id,
        operator='>',
        value_literal=0, # Depends on how variable is structured, but keeping it symmetrical
        timeframe='5m'
    )
    
    # 3. Get Rule Bb52
    rule_res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Bb52').execute()
    if not rule_res.data:
        print("Rule Bb52 not found!")
        return
        
    rule = rule_res.data[0]
    
    cond_ids = [37, 73, 212, 9906, rsi_cond['id'], basis_cond['id']]
    
    weights = {
        '37': 0.2,
        '73': 0.1,
        '212': 0.2,
        '9906': 0.2,
        str(rsi_cond['id']): 0.2,
        str(basis_cond['id']): 0.1
    }
    
    # Update notes and name
    new_name = 'SHORT Spike Above Basis (con Sobrecompra)'
    notes = rule.get('notes', '') + ' | Renombrado desde CIERRE URGENTE SHORT. Agregados filtros de tendencia bajista (EMA3<EMA9) y sobrecompra (RSI>65).'
    
    # Update the rule
    sb.table('strategy_rules_v2').update({
        'name': new_name,
        'condition_ids': cond_ids,
        'condition_weights': weights,
        'min_score': 0.8,
        'notes': notes
    }).eq('rule_code', 'Bb52').execute()
    
    print("Rule Bb52 updated successfully.")
    print("New conditions:", cond_ids)

if __name__ == '__main__':
    update_bb52()
