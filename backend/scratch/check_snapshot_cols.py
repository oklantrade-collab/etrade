from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table("market_snapshot").select("*").limit(1).execute()
if res.data:
    print(res.data[0].keys())
else:
    print("No data in market_snapshot")
