
import sys
import os
sys.path.append(os.getcwd())
from app.core.supabase_client import get_supabase

sb = get_supabase()
res = sb.table('strategy_rules_v2').select('*').ilike('rule_code', '%Dd51%').execute()
for r in res.data:
    print(f"RULE: {r['rule_code']} | NAME: {r['name']} | IDS: {r['condition_ids']} | WEIGHTS: {r['condition_weights']}")
    # Fetch details for each condition
    if r['condition_ids']:
        c_res = sb.table('strategy_conditions').select('*, variable:strategy_variables(*)').in_('id', r['condition_ids']).execute()
        for c in c_res.data:
            print(f"  COND: {c['id']} {c['name']} | VAR: {c['variable']['source_field'] if c['variable'] else 'N/A'} {c['operator']} {c['value_literal']}")
