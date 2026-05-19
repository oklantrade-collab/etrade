import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== SEARCHING FOR PNL NEAR -13.05 ===")
res = sb.table('forex_positions').select('*').execute()

for p in res.data:
    pnl = p.get('pnl_usd')
    if pnl is not None and -15.0 <= float(pnl) <= -11.0:
        print("-" * 50)
        for k, v in p.items():
            if v is not None and k not in ['entries', 'sl_exchange_order_id']:
                print(f"  {k}: {v}")
