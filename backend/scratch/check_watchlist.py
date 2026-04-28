from app.core.supabase_client import get_supabase
from datetime import date

sb = get_supabase()
today = date.today().isoformat()
res = sb.table("watchlist_daily").select("*").eq("date", today).execute()
print(f"Watchlist for {today}: {len(res.data or [])} items")
if res.data:
    print(f"Sample: {res.data[0]['ticker']}")
else:
    # Try latest
    res = sb.table("watchlist_daily").select("*").order("date", desc=True).limit(5).execute()
    print("Latest dates in watchlist:")
    for r in res.data:
        print(f"- {r['ticker']} on {r['date']}")
