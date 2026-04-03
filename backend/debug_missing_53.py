
from app.core.supabase_client import get_supabase
sb = get_supabase()

# Check Condition
cond = sb.table("strategy_conditions").select("*").eq("id", 53).maybe_single().execute()
print(f"Condition 53: {cond.data}")

# Check Variable
var = sb.table("strategy_variables").select("*").eq("id", 53).maybe_single().execute()
print(f"Variable 53: {var.data}")

# Check Rule Bb21
rule = sb.table("strategy_rules_v2").select("*").eq("rule_code", "Bb21").maybe_single().execute()
print(f"Rule Bb21: {rule.data}")
