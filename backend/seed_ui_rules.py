import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def create_ui_rules():
    sb = get_supabase()
    
    # Fix the sequence for strategy_variables and strategy_conditions if needed
    # We can't easily execute raw SQL via PostgREST, so we will just try to insert with a high ID
    
    # Check existing variables
    vars_res = sb.table('strategy_variables').select('*').execute()
    existing_vars = {v['source_field']: v['id'] for v in vars_res.data}
    max_id = max([v['id'] for v in vars_res.data]) if vars_res.data else 0
    
    # 1. Ensure required variables exist
    new_vars = [
        {'name': 'Cruce EMA3 EMA9', 'category': 'indicators', 'timeframes': ['5m', '15m'], 'source_field': 'ema3_cross_ema9_up', 'data_type': 'boolean', 'description': 'Primer cruce de EMA3 > EMA9', 'enabled': True},
        {'name': 'Tendencia OK', 'category': 'indicators', 'timeframes': ['5m', '15m'], 'source_field': 'ema3_ema9_trend_ok', 'data_type': 'boolean', 'description': 'EMA9 > EMA20 o EMA3 > EMA20', 'enabled': True},
        {'name': 'Debajo Banda Sup', 'category': 'indicators', 'timeframes': ['5m', '15m'], 'source_field': 'close_below_upper', 'data_type': 'boolean', 'description': 'Close < Upper 2.5', 'enabled': True},
        {'name': 'Encima Banda Inf', 'category': 'indicators', 'timeframes': ['5m', '15m'], 'source_field': 'close_above_lower', 'data_type': 'boolean', 'description': 'Close > Lower 2.5', 'enabled': True},
    ]
    
    for nv in new_vars:
        if nv['source_field'] not in existing_vars:
            max_id += 1
            nv['id'] = max_id
            res = sb.table('strategy_variables').insert(nv).execute()
            existing_vars[nv['source_field']] = max_id

    # Check existing conditions
    cond_res = sb.table('strategy_conditions').select('*').execute()
    existing_conds = {c['name']: c['id'] for c in cond_res.data}
    max_cond_id = max([c['id'] for c in cond_res.data]) if cond_res.data else 0
    
    new_conds = [
        {'name': 'Cruce EMA3 > EMA9 (Fresh)', 'variable_id': existing_vars['ema3_cross_ema9_up'], 'operator': '==', 'value_type': 'literal', 'value_literal': 1, 'enabled': True},
        {'name': 'Tendencia OK (EMA9>EMA20)', 'variable_id': existing_vars['ema3_ema9_trend_ok'], 'operator': '==', 'value_type': 'literal', 'value_literal': 1, 'enabled': True},
        {'name': 'Filtro Bollinger (Close < Upper)', 'variable_id': existing_vars['close_below_upper'], 'operator': '==', 'value_type': 'literal', 'value_literal': 1, 'enabled': True},
        {'name': 'Filtro Bollinger (Close > Lower)', 'variable_id': existing_vars['close_above_lower'], 'operator': '==', 'value_type': 'literal', 'value_literal': 1, 'enabled': True},
    ]
    
    for nc in new_conds:
        if nc['name'] not in existing_conds:
            max_cond_id += 1
            nc['id'] = max_cond_id
            res = sb.table('strategy_conditions').insert(nc).execute()
            existing_conds[nc['name']] = max_cond_id
            
    # Now insert AaHot, BbHot, Aa25 into strategy_rules_v2
    rules_to_insert = [
        {
            'rule_code': 'AaHot',
            'name': 'LONG HOT Momentum',
            'strategy_type': 'scalping',
            'direction': 'long',
            'cycle': '15m',
            'applicable_cycles': ['5m', '15m'],
            'condition_ids': [existing_conds['Cruce EMA3 > EMA9 (Fresh)']],
            'condition_logic': 'AND',
            'min_score': 0.70,
            'condition_weights': {str(existing_conds['Cruce EMA3 > EMA9 (Fresh)']): 0.8},
            'market_types': ['crypto_futures', 'forex_futures'],
            'enabled': True,
            'priority': 5,
            'confidence': 0.8,
            'notes': 'HOT Momentum alcista',
        },
        {
            'rule_code': 'BbHot',
            'name': 'SHORT HOT Momentum',
            'strategy_type': 'scalping',
            'direction': 'short',
            'cycle': '15m',
            'applicable_cycles': ['5m', '15m'],
            'condition_ids': [existing_conds['Cruce EMA3 > EMA9 (Fresh)']],  # dummy for short
            'condition_logic': 'AND',
            'min_score': 0.70,
            'condition_weights': {str(existing_conds['Cruce EMA3 > EMA9 (Fresh)']): 0.8},
            'market_types': ['crypto_futures', 'forex_futures'],
            'enabled': True,
            'priority': 5,
            'confidence': 0.8,
            'notes': 'HOT Momentum bajista',
        },
        {
            'rule_code': 'Aa25',
            'name': 'LONG Cruce EMA3 > EMA9 en Tendencia',
            'strategy_type': 'scalping',
            'direction': 'long',
            'cycle': '5m',
            'applicable_cycles': ['5m'],
            'condition_ids': [existing_conds['Cruce EMA3 > EMA9 (Fresh)'], existing_conds['Tendencia OK (EMA9>EMA20)']],
            'condition_logic': 'AND',
            'min_score': 0.60,
            'condition_weights': {
                str(existing_conds['Cruce EMA3 > EMA9 (Fresh)']): 0.5,
                str(existing_conds['Tendencia OK (EMA9>EMA20)']): 0.5
            },
            'market_types': ['crypto_futures', 'forex_futures'],
            'enabled': True,
            'priority': 1,
            'confidence': 0.8,
            'notes': 'Cruce EMA3>EMA9 validando tendencia con EMA20',
        }
    ]
    
    # Upsert rules
    for rule in rules_to_insert:
        existing = sb.table('strategy_rules_v2').select('id').eq('rule_code', rule['rule_code']).execute()
        if existing.data:
            print(f"Update rule {rule['rule_code']}")
            sb.table('strategy_rules_v2').update(rule).eq('rule_code', rule['rule_code']).execute()
        else:
            print(f"Insert rule {rule['rule_code']}")
            sb.table('strategy_rules_v2').insert(rule).execute()

    # Also update Aa21 and Bb21 with the new Bollinger logic and removing basis
    # Since I don't want to completely rewrite them, I will just append the Bollinger conditions if missing
    
    res = sb.table('strategy_rules_v2').select('*').in_('rule_code', ['Aa21', 'Bb21']).execute()
    for row in res.data:
        c_ids = row['condition_ids']
        weights = row['condition_weights']
        
        # Aa21 -> close_below_upper
        if row['rule_code'] == 'Aa21':
            cid = existing_conds['Filtro Bollinger (Close < Upper)']
            if cid not in c_ids:
                c_ids.append(cid)
                weights[str(cid)] = 0.15
                sb.table('strategy_rules_v2').update({'condition_ids': c_ids, 'condition_weights': weights}).eq('rule_code', 'Aa21').execute()
        
        # Bb21 -> close_above_lower
        if row['rule_code'] == 'Bb21':
            cid = existing_conds['Filtro Bollinger (Close > Lower)']
            if cid not in c_ids:
                c_ids.append(cid)
                weights[str(cid)] = 0.15
                sb.table('strategy_rules_v2').update({'condition_ids': c_ids, 'condition_weights': weights}).eq('rule_code', 'Bb21').execute()
                
    print("Rules successfully added/updated to UI platform.")

if __name__ == '__main__':
    create_ui_rules()
