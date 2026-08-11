import asyncio
from app.core.supabase_client import get_supabase
import json

async def check():
    sb = get_supabase()
    res = sb.table('strategy_conditions').select('id,name').ilike('name', '%EMA20%1h%').execute()
    print('Conditions matching EMA20 1h:', res.data)
    
if __name__ == '__main__':
    asyncio.run(check())
