
import os
from supabase import create_client, Client

url = "https://iriotnsoauqrfsjbqyyp.supabase.co"
key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

res = supabase.table("risk_config").select("*").execute()
for r in res.data:
    print(f"{r['key']}: {r['value']}")
