from app.core.supabase_client import get_supabase

sb = get_supabase()
res = sb.table("trades_journal").select("*").limit(1).execute()
if res.data:
    print(res.data[0].keys())
else:
    print("Table is empty.")
