import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== PRINTING ONE FOREX POSITION ===")
res = sb.table('forex_positions').select('*').limit(1).execute()

if res.data:
    p = res.data[0]
    for k, v in p.items():
        print(f"  {k}: {v}")
else:
    print("No positions found.")
