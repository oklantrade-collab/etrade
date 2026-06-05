import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

sb = get_supabase()

print("--- RECENT SYSTEM LOGS ---")
res = sb.table("system_logs").select("*").eq("module", "stocks_scheduler").ilike("message", "%Block%").order("created_at", desc=True).limit(20).execute()
for row in res.data:
    print(f"[{row['created_at']}] {row['level']} - {row['message']}")
