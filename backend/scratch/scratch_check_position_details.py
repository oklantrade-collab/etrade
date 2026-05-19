import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== POSITION DETAILS ===")
res = sb.table('positions').select('*').eq('id', '17f811f5-7eba-4966-8b4d-800adde2fa3e').execute()

if res.data:
    p = res.data[0]
    for k, v in p.items():
        print(f"  {k}: {v}")
else:
    print("Position not found.")
