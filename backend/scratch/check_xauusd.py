import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_xauusd_positions():
    sb = get_supabase()
    # Get config first
    config_res = sb.table('trading_config').select('*').execute()
    print("--- TRADING CONFIG ---")
    print(json.dumps(config_res.data, indent=2))
    
    # Get XAUUSD positions
    pos_res = sb.table('positions').select('*').eq('symbol', 'XAUUSD').execute()
    print("\n--- XAUUSD POSITIONS ---")
    if pos_res.data:
        for p in pos_res.data:
            print(json.dumps(p, indent=2))
    else:
        print("No XAUUSD positions found.")

if __name__ == "__main__":
    asyncio.run(check_xauusd_positions())
