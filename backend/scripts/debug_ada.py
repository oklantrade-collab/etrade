import os, sys, json
from datetime import datetime, timezone

sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase
import asyncio

async def main():
    sb = get_supabase()
    
    # Check max_positions_per_symbol
    risk_res = sb.table('risk_config').select('*').limit(1).execute()
    print("Risk config:", risk_res.data)

    trade_res = sb.table('trading_config').select('*').limit(1).execute()
    print("Trading config:", trade_res.data)
    
    pos_res = sb.table('positions').select('*').eq('symbol', 'ADAUSDT').eq('status', 'open').execute()
    print(f"\nADAUSDT open positions ({len(pos_res.data)}):")
    for p in pos_res.data:
        print(f" - {p['id'][:8]} | side={p['side']} | rule={p['rule_code']} | opened_at={p['opened_at']}")
        
if __name__ == '__main__':
    asyncio.run(main())
