import os
import json
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Query evaluations around 2026-05-15T06:32:00
# Let's search from 06:20 to 06:40
res = sb.table('strategy_evaluations')\
    .select('*')\
    .eq('symbol', 'GBPUSD')\
    .gte('created_at', '2026-05-15T06:20:00+00:00')\
    .lte('created_at', '2026-05-15T06:45:00+00:00')\
    .execute()

data = res.data or []
print(f"Found {len(data)} evaluations.")

for idx, ev in enumerate(data):
    print(f"Eval {idx+1}:")
    print(f"Time: {ev.get('created_at')}")
    print(f"Triggered: {ev.get('triggered')}")
    print(f"Direction: {ev.get('direction')}")
    print(f"Indicators:")
    # Print context/indicators if stored in database
    # Let's print the raw evaluation details
    for k, v in ev.items():
        if k not in ['id', 'created_at', 'symbol']:
            print(f"  {k}: {v}")
    print("-" * 50)
