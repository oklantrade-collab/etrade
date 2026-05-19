import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

res = sb.table('positions').select('*').eq('id', '93d5e6f1-2185-4017-b10d-ea72ad01f836').single().execute()
p = res.data

print("=== DETAILED POSITION INFO FOR TINY BTC ===")
for k, v in p.items():
    print(f"{k}: {v}")
