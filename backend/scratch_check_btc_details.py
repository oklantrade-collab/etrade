import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

try:
    res = sb.table('positions').select('*').eq('id', '93d5e6f1-2185-4017-b10d-ea72ad01f836').single().execute()
    pos = res.data
    print("=== POSITION DETAILS ===")
    for k, v in pos.items():
        print(f"  {k}: {v}")
except Exception as e:
    print("Error querying position details:", e)
