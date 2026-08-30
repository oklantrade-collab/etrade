import os
import sys
import dotenv
from supabase import create_client

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

res = sb.table("stocks_positions").select("*").limit(1).execute()
if res.data:
    print("Columns:", list(res.data[0].keys()))

update_res = sb.table("stocks_positions").update({
    "status": "closed"
}).eq("status", "open").execute()
print(f"Successfully closed {len(update_res.data)} stale stock positions in Supabase.")
