import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    res = sb.table('stocks_positions').select('*').eq('ticker', 'FCEL').eq('status', 'open').execute()
    print(f"FCEL POSITIONS: {res.data}")
    
    res = sb.table('market_snapshot').select('*').eq('symbol', 'FCEL').execute()
    print(f"FCEL SNAPSHOT: {res.data}")

if __name__ == "__main__":
    asyncio.run(check())
