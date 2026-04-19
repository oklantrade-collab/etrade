import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

res = sb.table("strategy_conditions").select("*").limit(500).execute()
if res.data:
    print(f"Total conditions found: {len(res.data)}")
    for c in res.data:
        # Looking for reversal/oversold/momentum/trend related conditions
        if any(term in c['name'].lower() or term in (c['description'] or '').lower() 
               for term in ['rsi', 'zone', 'psar', 'trend', 'mom', 'vol', 'cross', 'confirm', 'extre']):
             print(f"  ID {c['id']}: {c['name']} ({c['description']}) | Timeframe: {c['timeframe']}")
else:
    print("No conditions found.")
