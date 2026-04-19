import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Check strategy_conditions columns
res = sb.table("strategy_conditions").select("*").limit(1).execute()
if res.data:
    print(f"Columns: {list(res.data[0].keys())}")
    for c in res.data:
        print(f"Condition 1: {c}")
else:
    print("Table is empty (unlikely).")
