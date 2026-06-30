import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

sb = get_supabase()
rule_code = 'Aa12'
new_condition = {"indicator": "bb_lower_slope_positive", "operator": "==", "value": True}

# Only update trading_rules, as it stores JSON conditions and is used by the backend execution engine.
res = sb.table('trading_rules').select('*').eq('rule_code', rule_code).execute()
if res.data:
    rule = res.data[0]
    conditions = rule.get('conditions', [])
    
    # Check if condition is already there
    exists = any(c.get('indicator') == new_condition['indicator'] for c in conditions)
    if not exists:
        conditions.append(new_condition)
        sb.table('trading_rules').update({'conditions': conditions}).eq('rule_code', rule_code).execute()
        print(f"Updated trading_rules for {rule_code}")
    else:
        print(f"Condition already exists in trading_rules for {rule_code}")
