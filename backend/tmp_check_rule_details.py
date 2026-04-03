from app.core.supabase_client import get_supabase
import asyncio
import json
import sys

# Set encoding to utf-8
sys.stdout.reconfigure(encoding='utf-8')

async def check_rule_details():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Dd21_15m').execute()
    if res.data:
        rule = res.data[0]
        print(f"Rule: {rule['rule_code']}")
        print(f"Conditions: {rule['condition_ids']}")
        print(f"Weights: {rule['condition_weights']}")
        
        # Now get the conditions
        c_ids = rule['condition_ids']
        conds_res = sb.table('strategy_conditions').select('*, variable:strategy_variables(*)').in_('id', c_ids).execute()
        for c in conds_res.data:
            print(f"Cond ID: {c['id']}, Name: {c['name']}, Operator: {c['operator']}, Value: {c.get('value_literal') or c.get('value_list')}")

if __name__ == "__main__":
    asyncio.run(check_rule_details())
