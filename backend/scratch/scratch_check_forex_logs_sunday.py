import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== SEARCHING SYSTEM LOGS FOR POSITION CLOSURES ===")
pos_ids = ['c4439ce2-a423-48ea-84b6-487441fa02a1', 'dddc3cc7-6d14-4b0d-8b70-8815cc7ab9e0', '1f7757d8-6569-4a3c-b234-60a6f70331c3']

for pid in pos_ids:
    print(f"\nLogs for ID: {pid}")
    res = sb.table('system_logs') \
        .select('*') \
        .ilike('message', f'%{pid[:8]}%') \
        .order('created_at', desc=True) \
        .execute()
    
    print(f"Found {len(res.data)} logs:")
    for log in res.data:
        print(f"  [{log.get('created_at')}] [{log.get('level')}] {log.get('message')}")

# Also search broadly for REVERSION
print("\n=== SEARCHING SYSTEM LOGS FOR '[REVERSION]' ===")
res_rev = sb.table('system_logs') \
    .select('*') \
    .ilike('message', '%[REVERSION]%') \
    .gte('created_at', '2026-05-17T23:00:00+00:00') \
    .lte('created_at', '2026-05-17T23:59:59+00:00') \
    .execute()

print(f"Found {len(res_rev.data)} [REVERSION] logs:")
for log in res_rev.data:
    print(f"  [{log.get('created_at')}] [{log.get('level')}] {log.get('message')}")
