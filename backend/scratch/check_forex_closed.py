import os
import json
from app.core.supabase_client import get_supabase

sb = get_supabase()
res = sb.table("forex_positions").select("id, symbol, side, closed_at").eq("status", "closed").execute()
data = res.data or []
print(f"Total closed forex positions: {len(data)}")
