
import os
import json
from supabase import create_client
from dotenv import load_dotenv

def check_crypto_positions():
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    sb = create_client(url, key)
    
    print("--- Crypto Positions (positions table) ---")
    res = sb.table("positions").select("*").execute()
    print(json.dumps(res.data, indent=2))

if __name__ == "__main__":
    check_crypto_positions()
