import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.core.supabase_client import get_supabase

async def main():
    sb = get_supabase()
    res_cfg = sb.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
    print("=== TRADING CONFIG ===")
    print(res_cfg.data)
    
    res_rules = sb.table('trading_rules').select('rule_code, enabled').execute()
    print("\n=== TRADING RULES STATUS ===")
    for row in res_rules.data or []:
        print(row)
        
if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
