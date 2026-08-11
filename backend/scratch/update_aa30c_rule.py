import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

def update_rule():
    sb = get_supabase()
    
    # 1. Look for RSI < 60 condition
    rsi_res = sb.table('strategy_conditions').select('*').ilike('name', '%RSI%').execute()
    rsi_cond = None
    for c in rsi_res.data:
        if '60' in c['name'] or '60' in (c.get('description') or ''):
            rsi_cond = c
            break
            
    max_id_res = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
    next_id = (max_id_res.data[0]['id'] + 1) if max_id_res.data else 1
    
    if not rsi_cond:
        print(f"Inserting RSI < 60 condition with ID {next_id}...")
        new_rsi = {
            'id': next_id,
            'name': 'RSI < 60 5m',
            'description': 'RSI 5m por debajo de 60',
            'variable_id': 112,
            'operator': '<',
            'value_type': 'literal',
            'value_literal': 60,
            'timeframe': '5m',
            'enabled': True
        }
        res = sb.table('strategy_conditions').insert(new_rsi).execute()
        rsi_cond = res.data[0]
        next_id += 1
        
    # 2. Look for ADX > 25 5m condition
    adx_res = sb.table('strategy_conditions').select('*').ilike('name', '%ADX%').execute()
    adx_cond = None
    for c in adx_res.data:
        if '25' in c['name'] or '25' in (c.get('description') or ''):
            adx_cond = c
            break
            
    if not adx_cond:
        print(f"Inserting ADX > 25 condition with ID {next_id}...")
        new_adx = {
            'id': next_id,
            'name': 'ADX > 25 5m',
            'description': 'ADX 5m por encima de 25',
            'variable_id': 3,
            'operator': '>',
            'value_type': 'literal',
            'value_literal': 25,
            'timeframe': '5m',
            'enabled': True
        }
        res = sb.table('strategy_conditions').insert(new_adx).execute()
        adx_cond = res.data[0]
        
    print(f"RSI condition ID: {rsi_cond['id']}")
    print(f"ADX condition ID: {adx_cond['id']}")
    
    # 3. Update Rule Aa30C
    rule_res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa30C').execute()
    if not rule_res.data:
        print("Rule Aa30C not found!")
        return
        
    rule = rule_res.data[0]
    cond_ids = rule['condition_ids']
    
    if rsi_cond['id'] not in cond_ids:
        cond_ids.append(rsi_cond['id'])
    if adx_cond['id'] not in cond_ids:
        cond_ids.append(adx_cond['id'])
        
    weights = rule.get('condition_weights') or {}
    weights[str(rsi_cond['id'])] = 0.1
    weights[str(adx_cond['id'])] = 0.1
    
    # Update notes
    notes = rule.get('notes', '') + ' | Agregado filtro RSI<60 y ADX>25 en 5m.'
    
    # Update the rule
    sb.table('strategy_rules_v2').update({
        'condition_ids': cond_ids,
        'condition_weights': weights,
        'notes': notes
    }).eq('rule_code', 'Aa30C').execute()
    
    print("Rule updated successfully. New conditions:")
    print(cond_ids)

if __name__ == '__main__':
    update_rule()
