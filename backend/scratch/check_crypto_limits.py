from app.core.supabase_client import get_supabase
from datetime import datetime, timezone

sb = get_supabase()
limit = 4

res = sb.table('positions').select('*').eq('status', 'open').execute()
positions = res.data or []

from collections import defaultdict
counts = defaultdict(int)
for p in positions:
    counts[p['symbol']] += 1

print("Crypto Positions Count:")
for sym, count in counts.items():
    print(f"{sym}: {count}")
    if count > limit:
        print(f"  ⚠️ Warning: {sym} exceeds limit!")
