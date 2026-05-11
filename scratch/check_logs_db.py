import os
import json
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('backend/.env')

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

res = sb.table('system_logs').select('*').eq('module', 'forex_worker').order('created_at', desc=True).limit(20).execute()
for l in res.data:
    print(f"[{l['created_at']}] [{l['level']}] {l['message']}")
