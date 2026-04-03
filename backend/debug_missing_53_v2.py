
from app.core.supabase_client import get_supabase
sb = get_supabase()

# Using basic execute to see what comes back
try:
    res = sb.table("strategy_conditions").select("*").eq("id", 53).execute()
    print(f"Condition 53 Result: {res.data}")
except Exception as e:
    print(f"Error checking condition: {e}")

try:
    res = sb.table("strategy_rules_v2").select("*").eq("rule_code", "Bb21").execute()
    print(f"Rule Bb21 IDs: {res.data[0]['condition_ids']}")
    print(f"Rule Bb21 Weights: {res.data[0]['condition_weights']}")
except Exception as e:
    print(f"Error checking rule: {e}")
