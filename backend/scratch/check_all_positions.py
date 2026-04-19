
import os
import json
from supabase import create_client
from dotenv import load_dotenv

def check_all_positions():
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    sb = create_client(url, key)
    
    print("--- Forex Positions (All Statuses) ---")
    res = sb.table("forex_positions").select("symbol,side,entry_price,tp_price,sl_price,status").execute()
    print(json.dumps(res.data, indent=2))

if __name__ == "__main__":
    check_all_positions()
