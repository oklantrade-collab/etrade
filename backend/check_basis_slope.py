
from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table("strategy_variables").select("id, name, source_field").eq("name", "basis_slope").execute()
print(res.data)
res2 = sb.table("strategy_variables").select("id, name, source_field").eq("source_field", "basis_slope").execute()
print(res2.data)
