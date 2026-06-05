import asyncio
import os
import sys

sys.path.append(r'c:\Fuentes\eTrade\backend')

from app.core.supabase_client import get_supabase

async def main():
    sb = get_supabase()
    res = sb.table('stocks_priority_queue').select('*').order('apex_score_4h', desc=True).limit(3).execute()
    for row in res.data:
        print(f"--- {row['ticker']} ---")
        print(f"APEX 4H: {row['apex_score_4h']}")
        print(f"APEX detail: {row.get('apex_score_detail', 'N/A')}")
        
        # Let's also check the actual market_snapshot for that ticker
        snap = sb.table('market_snapshot').select('*').eq('symbol', row['ticker']).execute()
        if snap.data:
            s = snap.data[0]
            print(f"Snapshot APEX 4H: {s.get('apex_4h')}")
            if s.get('apex_detail'):
                print(f"Blocks: {s['apex_detail'].get('blocks')}")

if __name__ == '__main__':
    asyncio.run(main())
