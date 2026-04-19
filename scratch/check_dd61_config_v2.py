import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Check Dd61 rules columns
res = sb.table("strategy_rules_v2").select("*").limit(1).execute()
if res.data:
    print(f"Columns: {list(res.data[0].keys())}")
else:
    print("Table is empty (unlikely).")

# Correct script
res = sb.table("strategy_rules_v2").select("*").ilike("rule_code", "Dd61%").execute()
rules = res.data or []

print(f"\nFound {len(rules)} Dd61 rules:")
for r in rules:
    print(f"\nRule: {r['rule_code']}")
    print(f"  Enabled: {r.get('enabled')}")
    print(f"  Min Score: {r.get('min_score')}")
    print(f"  Weights: {r.get('condition_weights')}")

# Check conditions
cond_ids = set()
for r in rules:
    if r['condition_weights']:
        cond_ids.update(r['condition_weights'].keys())

if cond_ids:
    print("\nConditions involved:")
    cond_res = sb.table("rule_conditions_v2").select("*").in_("id", list(cond_ids)).execute()
    for c in (cond_res.data or []):
        print(f"  ID {c['id']}: {c['name']} (Condition Type: {c['condition_type']}, Params: {c['params']})")
