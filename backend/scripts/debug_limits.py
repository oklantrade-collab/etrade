import os, sys, json
from datetime import datetime, timezone

sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase
import asyncio

async def main():
    sb = get_supabase()
    
    risk_res = sb.table('risk_config').select('max_positions_per_symbol').limit(1).execute()
    print("Risk config limit:", risk_res.data)

    trade_res = sb.table('trading_config').select('max_positions_per_symbol').limit(1).execute()
    print("Trading config limit:", trade_res.data)
        
if __name__ == '__main__':
    asyncio.run(main())
