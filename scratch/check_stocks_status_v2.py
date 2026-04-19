import sys, os
from datetime import date
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()
today = date.today().isoformat()

print(f"Checking records for today: {today}")
try:
    res = sb.table("watchlist_daily").select("*").eq("date", today).limit(5).execute()
    if res.data:
        print(f"Found {len(res.data)} records for today.")
        for r in res.data:
            # Print available keys once
            if 'printed_keys' not in locals():
                print(f"Available keys: {list(r.keys())}")
                printed_keys = True
            print(f"  Ticker: {r['ticker']}, Price: {r.get('price')}")
    else:
        print("No records found for today in watchlist_daily.")
except Exception as e:
    print(f"Error querying watchlist_daily for today: {e}")

# Check latest data regardless of date
print("\nChecking latest records overall:")
try:
    res_latest = sb.table("watchlist_daily").select("*").order("date", desc=True).limit(5).execute()
    if res_latest.data:
        for r in res_latest.data:
            print(f"  Ticker: {r['ticker']}, Date: {r['date']}, Price: {r.get('price')}")
except Exception as e:
    print(f"Error querying watchlist_daily for latest: {e}")

# Check for specific IB logs
print("\nChecking for IB related messages in system_logs:")
try:
    res_logs = sb.table("system_logs").select("*").ilike("message", "%IB%").order("timestamp", desc=True).limit(10).execute()
    if res_logs.data:
        for l in res_logs.data:
            print(f"  [{l['timestamp']}] {l['level']}: {l['message']}")
    else:
        print("No IB logs found in system_logs.")
except Exception as e:
    print(f"Could not read system_logs: {e}")
