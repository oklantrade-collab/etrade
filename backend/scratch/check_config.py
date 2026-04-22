
import os
from supabase import create_client, Client

url = "https://iriotnsoauqrfsjbqyyp.supabase.co"
key = os.getenv("SUPABASE_KEY")
if not key:
    print("Error: SUPABASE_KEY not found in env")
    exit(1)

supabase: Client = create_client(url, key)

res = supabase.table("stocks_config").select("*").in_("key", ["total_capital_usd", "risk_per_operation_pct", "capital_assigned"]).execute()
print(res.data)
