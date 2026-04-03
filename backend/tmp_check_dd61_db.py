import asyncio
from app.core.supabase_client import get_supabase
import json

async def check_dd61():
    sb = get_supabase()
    
    # Check rule Dd61_15m
    rule_res = sb.table('strategy_rules_v2').select('*').ilike('rule_code', 'Dd61%').execute()
    print("--- RULES ---")
    for r in rule_res.data:
        print(f"Code: {r['rule_code']} | Logic: {r['condition_logic']} | Min Score: {r['min_score']} | Weights: {r['condition_weights']}")
        cond_ids = r['condition_ids']
        
        # Check conditions for this rule
        conds_res = sb.table('strategy_conditions').select('*, variable:strategy_variables(*)').in_('id', cond_ids).execute()
        print("  Conditions:")
        for c in conds_res.data:
            var = c.get('variable', {})
            print(f"    ID: {c['id']} | Name: {c['name']} | Var: {var.get('name')} ({var.get('source_field')}) | Op: {c['operator']} | Val: {c.get('value_literal')}")

if __name__ == "__main__":
    asyncio.run(check_dd61())
