import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== trading_config ===")
cfg = sb.table('trading_config').select('*').eq('id', 1).single().execute()
for k, v in cfg.data.items():
    print(f"  {k}: {v}")

print("\n=== risk_config ===")
rc = sb.table('risk_config').select('*').limit(1).execute()
if rc.data:
    for k, v in rc.data[0].items():
        print(f"  {k}: {v}")
else:
    print("  No risk_config found")
