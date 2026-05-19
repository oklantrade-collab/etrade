import os
import json
from app.core.supabase_client import get_supabase

sb = get_supabase()
res = sb.table("positions").select("id, symbol, side, closed_at").eq("status", "closed").execute()
data = res.data or []
print(f"Total closed positions in database: {len(data)}")
if data:
    print(f"First few in DB query: {data[:5]}")
