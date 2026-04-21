import os
import sys
sys.path.append('backend')
from dotenv import load_dotenv
load_dotenv('backend/.env')
from app.core.supabase_client import get_supabase

async def check_columns():
    sb = get_supabase()
    res = sb.table('stocks_orders').select('*').limit(1).execute()
    if res.data:
        print(f"Columns in stocks_orders: {list(res.data[0].keys())}")
        
    res2 = sb.table('stocks_positions').select('*').limit(1).execute()
    if res2.data:
        print(f"Columns in stocks_positions: {list(res2.data[0].keys())}")

    res3 = sb.table('trading_config').select('*').limit(1).execute()
    if res3.data:
        print(f"Columns in trading_config: {list(res3.data[0].keys())}")

    res4 = sb.table('risk_config').select('*').limit(1).execute()
    if res4.data:
        print(f"Columns in risk_config: {list(res4.data[0].keys())}")

    res5 = sb.table('stocks_config').select('*').execute()
    if res5.data:
        print(f"Keys in stocks_config: {[r['key'] for r in res5.data]}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(check_columns())
