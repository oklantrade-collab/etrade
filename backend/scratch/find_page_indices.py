import os
from app.core.supabase_client import get_supabase

sb = get_supabase()
res = sb.table("forex_positions").select("symbol, closed_at").eq("status", "closed").order("opened_at", desc=True).execute()
data = res.data or []
print(f"Total items: {len(data)}")
for idx, item in enumerate(data):
    closed_at = item.get("closed_at") or ""
    if "2026-05-11" in closed_at:
        print(f"Index: {idx}, Page (1-based): {idx // 10 + 1}, closed_at: {closed_at}")
