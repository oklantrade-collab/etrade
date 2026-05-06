import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_duplicate_crypto():
    sb = get_supabase()
    try:
        res = sb.table("positions").select("*").eq("status", "open").execute()
        print(f"Found {len(res.data)} OPEN Crypto positions.")
        counts = {}
        for p in res.data:
            s = p['symbol']
            counts[s] = counts.get(s, []) + [p]
            
        for s, positions in counts.items():
            print(f"--- Symbol {s} has {len(positions)} positions ---")
            for p in positions:
                print(f"  [{p['opened_at']}] {p['side']} Entry: {p['entry_price']} Rule: {p.get('rule_code')}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_duplicate_crypto())
