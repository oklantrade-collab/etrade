import os
import sys
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timedelta, timezone

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== RECENT SYSTEM ERROR LOGS ===")
since = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
res = sb.table('system_logs').select('*').gte('created_at', since).order('created_at', desc=True).limit(50).execute()

for r in res.data:
    msg = r.get('message', '')
    if any(x in msg.lower() for x in ['error', 'nameerror', 'except', 'defined', 'fail']):
        print(f"[{r.get('created_at')}] [{r.get('module')}] {msg[:300]}")
