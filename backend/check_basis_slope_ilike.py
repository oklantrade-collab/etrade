
from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table("strategy_variables").select("id, name, source_field").ilike("name", "basis_slope").execute()
print(res.data)
