import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Check Dd61 rules
res = sb.table("strategy_rules_v2").select("*").ilike("rule_code", "Dd61%").execute()
rules = res.data or []

# Deactivate Dd61 rules as requested
for r in rules:
    print(f"Deactivating {r['rule_code']} (Current State: Enabled={r['enabled']})")
    sb.table("strategy_rules_v2").update({"enabled": False, "notes": "Deactivada por performance negativa (EV=-0.1431, WinRate=47.1%)"}).eq("id", r["id"]).execute()

# Check conditions
cond_ids = set()
for r in rules:
    if r['condition_weights']:
        cond_ids.update(r['condition_weights'].keys())

if cond_ids:
    print("\nConditions involved in Dd61:")
    cond_res = sb.table("strategy_conditions").select("*").in_("id", [int(cid) for cid in cond_ids if cid.isdigit()]).execute()
    for c in (cond_res.data or []):
        print(f"  ID {c['id']}: {c['name']} ({c['variable_id']} {c['operator']} {c['value_literal'] or c['value_list']})")
else:
    print("\nNo condition weights found.")
