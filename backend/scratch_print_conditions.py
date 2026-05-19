import os
import sys
import asyncio
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, os.path.join(os.getcwd(), '..'))

async def main():
    load_dotenv('.env')
    sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))
    
    print("Strategy Conditions:")
    for cid in [58, 59, 60]:
        res = sb.table('strategy_conditions').select('*').eq('id', cid).execute()
        if res.data:
            print(res.data[0])
        else:
            print(f"Condition {cid} not found.")

if __name__ == "__main__":
    asyncio.run(main())
