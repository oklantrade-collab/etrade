import os
import dotenv
from datetime import datetime, timezone
from supabase import create_client

root_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

pos_id = '1f2aa7d4-d81f-47d6-acde-02faf6743521'
fields = {
    "current_price": 0.19268,
    "unrealized_pnl": 1.92,
    "size": 378.0,
    "updated_at": datetime.now(timezone.utc).isoformat()
}

for k, v in fields.items():
    try:
        r = sb.table("positions").update({k: v}).eq("id", pos_id).execute()
        print(f"Field '{k}' OK!")
    except Exception as e:
        print(f"Field '{k}' FAILED: {e}")
