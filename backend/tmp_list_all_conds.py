import asyncio
from app.core.supabase_client import get_supabase
import json

async def list_all_conditions():
    sb = get_supabase()
    
    conds_res = sb.table('strategy_conditions').select('*, variable:strategy_variables(*)').execute()
    print("--- ALL CONDITIONS ---")
    for c in conds_res.data:
        var = c.get('variable', {})
        print(f"ID: {c['id']} | Name: {c['name']} | Var: {var.get('name')} | Op: {c['operator']} | Val: {c.get('value_literal')}")

async def check_rule_ids():
    sb = get_supabase()
    rule_res = sb.table('strategy_rules_v2').select('*').ilike('rule_code', 'Dd61%').execute()
    for r in rule_res.data:
        print(f"Rule: {r['rule_code']} | Condition IDs: {r['condition_ids']}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(list_all_conditions())
    loop.run_until_complete(check_rule_ids())
