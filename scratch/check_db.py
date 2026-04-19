import requests
r = requests.get('http://localhost:8080/api/v1/stocks/universe')
d = r.json()
print(f"Date from API: {d.get('date')}")
print(f"Total: {d['total']}")

# Check if all have same date
dates = set()
for u in d['universe'][:5]:
    # The API doesn't return date but let's see what pool_type we get
    print(f"  {u['ticker']}: pool_type='{u['pool_type']}', source from pool?")
    
# Also check raw watchlist_daily via direct Supabase query
print("\n--- Checking raw DB data ---")
import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase
sb = get_supabase()
from datetime import date
today = date.today().isoformat()
print(f"Today: {today}")

# Check today's data
res = sb.table("watchlist_daily").select("ticker, date, pool_type, price, fundamental_score, revenue_growth_yoy, gross_margin").eq("date", today).limit(5).execute()
print(f"\nToday's records ({today}): {len(res.data or [])}")
for r in (res.data or [])[:5]:
    print(f"  {r}")

# Check latest data regardless of date
res2 = sb.table("watchlist_daily").select("ticker, date, pool_type, price, fundamental_score").order("date", desc=True).limit(5).execute()
print(f"\nLatest records:")
for r in (res2.data or [])[:5]:
    print(f"  {r}")
