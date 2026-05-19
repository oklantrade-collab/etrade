import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== EXACT SUNDAY 17-MAY TRADES ===")
res = sb.table('forex_positions') \
    .select('*') \
    .gte('opened_at', '2026-05-17T23:00:00+00:00') \
    .lte('opened_at', '2026-05-17T23:59:59+00:00') \
    .execute()

print(f"Total positions opened on Sunday evening: {len(res.data)}")
for p in res.data:
    print("-" * 50)
    for k, v in p.items():
        if k not in ['entries', 'sl_exchange_order_id']:
            print(f"  {k}: {v}")
