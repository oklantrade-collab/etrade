from app.core.supabase_client import get_supabase

sb = get_supabase()
res = sb.table("stocks_positions").select("*").eq("status", "open").execute()
print(f"Active positions: {len(res.data or [])}")
for p in res.data:
    print(f"- {p['ticker']}: {p['shares']} shares")
