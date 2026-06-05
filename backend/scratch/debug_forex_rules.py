import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')
load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

target_rules = ['AaHot', 'BbHot', 'Aa21', 'Bb21']

print("=== FOREX RULES & CONDITIONS DETAIL ===")
res = sb.table('strategy_rules_v2').select('*').in_('rule_code', target_rules).execute()

for r in res.data:
    print(f"\nRule: {r['rule_code']} (ID: {r['id']}) - {r['name']}")
    print(f"  Direction: {r['direction']} | Cycle: {r['cycle']} | Enabled: {r['enabled']}")
    print(f"  Logic: {r['condition_logic']} | Min Score: {r['min_score']}")
    print(f"  Condition IDs: {r['condition_ids']}")
    print(f"  Condition Weights: {r['condition_weights']}")
    
    if r['condition_ids']:
        # Fetch the conditions detail
        conds = sb.table('strategy_conditions').select('*, variable:strategy_variables(*)').in_('id', r['condition_ids']).execute()
        print("  Conditions:")
        for c in conds.data:
            var = c.get('variable') or {}
            field = var.get('source_field', 'N/A')
            print(f"    - ID {c['id']}: {c['name']} (Variable Field: {field}) | Op: {c['operator']} | Lit: {c.get('value_literal')} | Var: {c.get('value_variable')} | List: {c.get('value_list')}")
    print("-" * 60)
