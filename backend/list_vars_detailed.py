
from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table("strategy_variables").select("id, name, source_field").execute()
for r in res.data:
    print(f"{r['id']}: {r['name']} ({r['source_field']})")
