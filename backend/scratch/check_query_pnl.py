import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_query_pnl():
    sb = get_supabase()
    # Try different ways to find those rows
    res = sb.table('forex_positions').select('*').gt('abs(pnl_usd)', 10).execute() # Note: abs() might not work in filter
    print(f"Result for gt 10: {len(res.data)}")
    
    res = sb.table('forex_positions').select('*').lt('pnl_usd', -10).execute()
    print(f"Result for lt -10: {len(res.data)}")
    for p in res.data:
        print(p)

    res = sb.table('forex_positions').select('*').gt('pnl_usd', 10).execute()
    print(f"Result for gt +10: {len(res.data)}")
    for p in res.data:
        print(p)

if __name__ == "__main__":
    asyncio.run(check_query_pnl())
