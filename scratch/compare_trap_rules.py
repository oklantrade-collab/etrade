import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Check Dd51 (Short Trap) vs Dd61 (Long Trap)
res = sb.table("strategy_rules_v2").select("*").ilike("rule_code", "Dd51%").execute()
print(f"Dd51 rules: {len(res.data or [])}")
for r in (res.data or []):
    print(f"  {r['rule_code']}: Min Score={r['min_score']}, Weights={r['condition_weights']}, Enabled={r['enabled']}")

res2 = sb.table("strategy_rules_v2").select("*").ilike("rule_code", "Dd61%").execute()
print(f"\nDd61 rules: {len(res2.data or [])}")
for r in (res2.data or []):
    print(f"  {r['rule_code']}: Min Score={r['min_score']}, Weights={r['condition_weights']}, Enabled={r['enabled']}")
