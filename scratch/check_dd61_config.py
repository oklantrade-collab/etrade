import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Check Dd61 rules
res = sb.table("strategy_rules_v2").select("*").ilike("rule_code", "Dd61%").execute()
rules = res.data or []

print(f"Found {len(rules)} Dd61 rules:")
for r in rules:
    print(f"\nRule: {r['rule_code']}")
    print(f"  Enabled: {r['enabled']}")
    print(f"  Min Score: {r['min_score']}")
    print(f"  Condition Weights: {r['condition_weights']}")
    print(f"  Default SL Pct: {r['default_sl_pct']}")
    print(f"  Default TP Pct: {r['default_tp_pct']}")
    print(f"  Notes: {r['notes']}")

# Check conditions for Dd61
cond_ids = set()
for r in rules:
    if r['condition_weights']:
        cond_ids.update(r['condition_weights'].keys())

if cond_ids:
    print("\nConditions involved:")
    cond_res = sb.table("rule_conditions_v2").select("*").in_("id", list(cond_ids)).execute()
    for c in (cond_res.data or []):
        print(f"  ID {c['id']}: {c['name']} (Condition Type: {c['condition_type']}, Params: {c['params']})")
else:
    print("\nNo condition weights found.")
