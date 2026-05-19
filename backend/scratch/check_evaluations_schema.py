import os
import json
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Query latest 5 evaluations
res = sb.table('strategy_evaluations')\
    .select('*')\
    .limit(5)\
    .execute()

data = res.data or []
print(f"Latest evaluations count: {len(data)}")
if data:
    for idx, ev in enumerate(data):
        print(f"Eval {idx+1}: {ev.get('symbol')} at {ev.get('created_at')}")
        for k, v in ev.items():
            print(f"  {k}: {v}")
        print("-" * 40)
else:
    print("No evaluations found in database.")
