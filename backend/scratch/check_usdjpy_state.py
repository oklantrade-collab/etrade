
import os
import json
from supabase import create_client
from dotenv import load_dotenv

def check_db():
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not found in environment.")
        return
        
    sb = create_client(url, key)
    
    print("--- Market Snapshot USDJPY ---")
    res = sb.table("market_snapshot").select("*").eq("symbol", "USDJPY").execute()
    print(json.dumps(res.data, indent=2))
    
    print("\n--- Open Forex Positions USDJPY ---")
    res = sb.table("forex_positions").select("*").eq("symbol", "USDJPY").eq("status", "open").execute()
    print(json.dumps(res.data, indent=2))

if __name__ == "__main__":
    check_db()
