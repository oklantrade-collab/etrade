import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')
load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

async def main():
    # Check max IDs
    var_res = sb.table('strategy_variables').select('id').order('id', desc=True).limit(1).execute()
    cond_res = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
    
    max_var_id = var_res.data[0]['id'] if var_res.data else 0
    max_cond_id = cond_res.data[0]['id'] if cond_res.data else 0
    
    print(f"Max variable ID: {max_var_id}")
    print(f"Max condition ID: {max_cond_id}")

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
