import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== FOREX TRADES JOURNAL FOR EURUSD ===")
res = sb.table('trades_journal') \
    .select('*') \
    .eq('ticker', 'EURUSD') \
    .order('exit_date', desc=True) \
    .limit(10) \
    .execute()

for t in res.data:
    print("-" * 50)
    for k, v in t.items():
         print(f"  {k}: {v}")
