import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# Check relevant conditions for reversal/rebound
res = sb.table("strategy_conditions").select("*").ilike("description", "%RSI%").execute()
if res.data:
    print(f"RSI Conditions:")
    for c in res.data:
        print(f"  ID {c['id']}: {c['name']} ({c['description']})")

res2 = sb.table("strategy_conditions").select("*").ilike("description", "%confirm%").execute()
if res2.data:
    print(f"\nConfirmation Conditions:")
    for c in res2.data:
        print(f"  ID {c['id']}: {c['name']} ({c['description']})")

res3 = sb.table("strategy_conditions").select("*").ilike("description", "%SAR%").execute()
if res3.data:
    print(f"\nSAR Conditions:")
    for c in res3.data:
        print(f"  ID {c['id']}: {c['name']} ({c['description']})")
