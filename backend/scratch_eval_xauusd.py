import asyncio
import os
import sys

sys.path.append(r'c:\Fuentes\eTrade\backend')

from app.core.supabase_client import get_supabase

async def main():
    sb = get_supabase()
    # Let's get evaluations for Aa21 today for XAUUSD
    res = sb.table('strategy_evaluations').select('*').eq('symbol', 'XAUUSD').eq('rule_code', 'Aa21').order('created_at', desc=True).limit(20).execute()
    
    print("Recent evaluations for XAUUSD Aa21:")
    for row in res.data:
        print(f"Time: {row['created_at']}, Score: {row['score']}, Triggered: {row['triggered']}")
        print(f"Context: {row.get('context')}")

if __name__ == '__main__':
    asyncio.run(main())
