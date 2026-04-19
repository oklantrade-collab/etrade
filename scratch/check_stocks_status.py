import sys, os
from datetime import date
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()
today = date.today().isoformat()

print(f"Checking records for today: {today}")
res = sb.table("watchlist_daily").select("ticker, date, last_updated").eq("date", today).order("last_updated", desc=True).limit(5).execute()

if res.data:
    print(f"Found {len(res.data)} records for today.")
    for r in res.data:
        print(f"  Ticker: {r['ticker']}, Last Updated: {r['last_updated']}")
else:
    print("No records found for today in watchlist_daily.")

# Check for any records from any date to see the latest
print("\nChecking latest records overall:")
res_latest = sb.table("watchlist_daily").select("ticker, date, last_updated").order("last_updated", desc=True).limit(5).execute()
if res_latest.data:
    for r in res_latest.data:
        print(f"  Ticker: {r['ticker']}, Date: {r['date']}, Last Updated: {r['last_updated']}")

# Check logs for stocks_scheduler
print("\nChecking latest stocks_scheduler logs (from system_logs table if exists):")
try:
    res_logs = sb.table("system_logs").select("*").eq("module", "stocks_scheduler").order("timestamp", desc=True).limit(5).execute()
    if res_logs.data:
        for l in res_logs.data:
            print(f"  [{l['timestamp']}] {l['level']}: {l['message']}")
    else:
        print("No stocks_scheduler logs found in system_logs.")
except Exception as e:
    print(f"Could not read system_logs: {e}")
