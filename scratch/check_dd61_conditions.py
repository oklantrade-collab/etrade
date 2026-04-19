import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Check Dd61 rules
res = sb.table("strategy_rules_v2").select("*").ilike("rule_code", "Dd61%").execute()
rules = res.data or []

print(f"Dd61 Logic (Enabled: {rules[0]['enabled'] if rules else 'N/A'})")

# Check conditions
cond_ids = set()
for r in rules:
    if r['condition_weights']:
        cond_ids.update(r['condition_weights'].keys())

if cond_ids:
    print("\nConditions involved:")
    # We suspect the table is 'strategy_conditions'
    try:
        cond_res = sb.table("strategy_conditions").select("*").in_("id", [int(cid) for cid in cond_ids if cid.isdigit()]).execute()
        for c in (cond_res.data or []):
            print(f"  ID {c['id']}: {c['name']} (Condition Type: {c['condition_type']}, Params: {c['params']})")
    except Exception as e:
        print(f"Error querying conditions: {e}")
else:
    print("\nNo condition weights found.")
