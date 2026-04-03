
from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table("strategy_variables").select("id, name").execute()
for r in res.data:
    print(f"{r['id']}: {r['name']}")
