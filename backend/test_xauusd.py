import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
import json

async def main():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').eq('status', 'open').execute()
    print(json.dumps(res.data, indent=2))

asyncio.run(main())
