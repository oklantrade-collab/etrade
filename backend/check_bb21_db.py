
from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table("strategy_rules_v2").select("*").eq("rule_code", "Bb21").single().execute()
print(res.data)
