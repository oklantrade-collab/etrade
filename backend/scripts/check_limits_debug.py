import os, sys, json
from datetime import datetime, timezone

sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase
from app.core.memory_store import BOT_STATE
from app.workers.scheduler import sync_db_config_to_memory
import asyncio

async def main():
    sb = get_supabase()
    
    # Check max_positions_per_symbol
    risk_res = sb.table('risk_config').select('*').limit(1).execute()
    print("Risk config:", risk_res.data)
    
    # Check positions for BTCUSDT
    pos_res = sb.table('positions').select('*').eq('symbol', 'BTCUSDT').eq('status', 'open').execute()
    print(f"BTCUSDT open positions ({len(pos_res.data)}):")
    for p in pos_res.data:
        print(f" - {p['id'][:8]} | side={p['side']} | reason={p['close_reason']} | status={p['status']}")
        
    pos_res2 = sb.table('positions').select('*').eq('symbol', 'BTC/USDT').eq('status', 'open').execute()
    print(f"BTC/USDT open positions ({len(pos_res2.data)}):")
    
if __name__ == '__main__':
    asyncio.run(main())
