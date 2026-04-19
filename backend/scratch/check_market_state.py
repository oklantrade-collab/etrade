
import os
import json
from supabase import create_client
from dotenv import load_dotenv

def check_market():
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    sb = create_client(url, key)
    
    print("--- Market Snapshot (All) ---")
    res = sb.table("market_snapshot").select("symbol,price,fibonacci_zone,sar_trend_4h,sar_trend_15m,mtf_score,pinescript_signal").execute()
    print(json.dumps(res.data, indent=2))
    
    print("\n--- Open Forex Positions ---")
    res = sb.table("forex_positions").select("*").eq("status", "open").execute()
    print(json.dumps(res.data, indent=2))

if __name__ == "__main__":
    check_market()
