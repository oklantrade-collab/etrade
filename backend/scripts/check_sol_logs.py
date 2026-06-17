import os
import sys
from supabase import create_client

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import dotenv
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")
sb = create_client(url, key)

print("--- SOLUSDT LOGS AROUND 14:30 UTC ---")
res2 = sb.table("pilot_diagnostics").select("*").eq("symbol", "SOLUSDT").order("id", desc=True).limit(30).execute()
for r in res2.data:
    print(r.get('created_at'), r.get('action'), r.get('reason'), r.get('rule_code'))
