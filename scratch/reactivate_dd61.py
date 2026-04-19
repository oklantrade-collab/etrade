import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Reactivate Dd61 rules
res = sb.table("strategy_rules_v2").select("*").ilike("rule_code", "Dd61%").execute()
rules = res.data or []

for r in rules:
    print(f"Reactivating {r['rule_code']} (Current State: Enabled={r['enabled']})")
    sb.table("strategy_rules_v2").update({"enabled": True, "notes": "Reactivada para mejora de lógica."}).eq("id", r["id"]).execute()

print("Reactivation complete.")
