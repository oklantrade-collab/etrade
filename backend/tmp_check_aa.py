import asyncio
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('*').in_('rule_code', ['Aa11', 'Aa12']).execute()
    for r in res.data:
        print(f"RULE: {r['rule_code']} ({r['name']})")
        print(f"  Min Score: {r['min_score']}")
        print(f"  Condition IDs: {r['condition_ids']}")
        print(f"  Weights: {r['condition_weights']}")
        
        # Fetch condition details
        c_res = sb.table('strategy_conditions').select('*, variable:strategy_variables(*)').in_('id', r['condition_ids']).execute()
        for c in c_res.data:
            print(f"    Cond {c['id']}: {c['name']} (Source: {c['variable']['source_field']}) Weight: {r['condition_weights'].get(str(c['id']))}")

if __name__ == "__main__":
    asyncio.run(check())
