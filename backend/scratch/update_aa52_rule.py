import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

def update_aa52():
    sb = get_supabase()
    
    # 1. Look for RSI < 35 condition
    rsi_res = sb.table('strategy_conditions').select('*').ilike('name', '%RSI%').execute()
    rsi_cond = None
    for c in rsi_res.data:
        if '35' in c['name'] or '35' in (c.get('description') or ''):
            rsi_cond = c
            break
            
    if not rsi_cond:
        max_id_res = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
        next_id = (max_id_res.data[0]['id'] + 1) if max_id_res.data else 1
        
        print(f"Inserting RSI < 35 condition with ID {next_id}...")
        new_rsi = {
            'id': next_id,
            'name': 'RSI < 35 5m',
            'description': 'RSI 5m por debajo de 35 (Sobrevenda)',
            'variable_id': 112,
            'operator': '<',
            'value_type': 'literal',
            'value_literal': 35,
            'timeframe': '5m',
            'enabled': True
        }
        res = sb.table('strategy_conditions').insert(new_rsi).execute()
        rsi_cond = res.data[0]
        
    print(f"RSI condition ID: {rsi_cond['id']}")
    
    # 2. Update Rule Aa52
    rule_res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa52').execute()
    if not rule_res.data:
        print("Rule Aa52 not found!")
        return
        
    rule = rule_res.data[0]
    cond_ids = rule['condition_ids']
    
    if rsi_cond['id'] not in cond_ids:
        cond_ids.append(rsi_cond['id'])
        
    weights = rule.get('condition_weights') or {}
    weights[str(rsi_cond['id'])] = 0.2
    
    # Update notes and name
    new_name = 'LONG Dip Below Basis (con Sobrevenda)'
    notes = rule.get('notes', '') + ' | Renombrado desde CIERRE URGENTE LONG. Agregado filtro RSI<35 en 5m para evitar atrapar cuchillos cayendo.'
    
    # Update the rule
    sb.table('strategy_rules_v2').update({
        'name': new_name,
        'condition_ids': cond_ids,
        'condition_weights': weights,
        'notes': notes
    }).eq('rule_code', 'Aa52').execute()
    
    print("Rule Aa52 updated successfully.")
    print("New conditions:", cond_ids)

if __name__ == '__main__':
    update_aa52()
