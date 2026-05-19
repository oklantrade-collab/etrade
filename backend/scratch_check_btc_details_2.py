import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

try:
    res = sb.table('positions').select('*').eq('id', 'fba0a3ad-bd76-4d2a-929a-cb26462d7e36').single().execute()
    pos = res.data
    print("=== POSITION DETAILS ===")
    for k, v in pos.items():
        print(f"  {k}: {v}")
except Exception as e:
    print("Error querying position details:", e)
