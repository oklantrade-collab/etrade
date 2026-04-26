
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append('c:/Fuentes/eTrade/backend')
load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.core.supabase_client import get_supabase

def dump_rules():
    sb = get_supabase()
    codes = ['Aa31a', 'Aa31b']
    
    res = sb.table('strategy_rules_v2').select('*').in_('rule_code', codes).execute()
    if not res.data:
        print("No se encontraron las reglas Aa31a o Aa31b.")
        return
    
    for rule in res.data:
        print(f"\n=== RULE: {rule['rule_code']} ({rule['name']}) ===")
        print(f"Logic: {rule.get('condition_logic')}")
        print(f"Min Score: {rule.get('min_score')}")
        print(f"Cycle: {rule.get('cycle')}")
        print(f"Applicable Cycles: {rule.get('applicable_cycles')}")
        
        cond_ids = rule.get('condition_ids', [])
        weights = rule.get('condition_weights', {})
        
        if cond_ids:
            cond_res = sb.table('strategy_conditions').select('*, variable:strategy_variables(*)').in_('id', cond_ids).execute()
            for cond in cond_res.data:
                var = cond.get('variable', {})
                print(f"  - Condition {cond['id']}: {cond['name']}")
                print(f"    Variable: {var.get('name')} (Source: {var.get('source_field')})")
                print(f"    Operator: {cond.get('operator')} | Value: {cond.get('value_literal') or cond.get('value_variable') or cond.get('value_list')}")
                print(f"    Weight: {weights.get(str(cond['id']))}")
        else:
            print("  No conditions found.")

if __name__ == "__main__":
    dump_rules()
