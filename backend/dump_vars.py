
from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table("strategy_variables").select("*").execute()
for r in res.data:
    print(r)
