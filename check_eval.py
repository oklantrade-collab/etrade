import asyncio
import sys
sys.path.append('.')
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    res = sb.table('forex_symbols').select('*').eq('symbol', 'USDJPY').execute()
    print('forex_symbols:', res.data)

    res = sb.table('market_snapshot').select('*').eq('symbol', 'USDJPY').execute()
    print('market_snapshot updated_at:', [x.get('updated_at') for x in res.data])

asyncio.run(check())
