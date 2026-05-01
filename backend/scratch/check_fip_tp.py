import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

async def check_fip():
    sb = get_supabase()
    res = sb.table('stocks_positions').select('*').eq('ticker', 'FIP').eq('status', 'open').execute()
    if res.data:
        p = res.data[0]
        import json
        print(json.dumps(p, indent=2, default=str))
    else:
        print("FIP is not open in stocks_positions.")

if __name__ == "__main__":
    asyncio.run(check_fip())
