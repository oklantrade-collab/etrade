import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.core.supabase_client import get_supabase
import asyncio

async def inspect_db():
    sb = get_supabase()
    
    # 1. Closed stocks positions
    res = sb.table('stocks_positions').select('id, ticker, unrealized_pnl, updated_at').eq('status', 'closed').order('updated_at', desc=True).limit(10).execute()
    print("Recent closed stock positions:")
    for row in res.data:
        print(row)
        
    # 2. Closed crypto positions
    res_c = sb.table('positions').select('id, symbol, realized_pnl, closed_at').eq('status', 'closed').order('closed_at', desc=True).limit(10).execute()
    print("\nRecent closed crypto positions:")
    for row in res_c.data:
        print(row)
        
    # 3. Closed forex positions
    res_f = sb.table('forex_positions').select('id, symbol, pnl_usd, closed_at').eq('status', 'closed').order('closed_at', desc=True).limit(10).execute()
    print("\nRecent closed forex positions:")
    for row in res_f.data:
        print(row)

if __name__ == "__main__":
    asyncio.run(inspect_db())
