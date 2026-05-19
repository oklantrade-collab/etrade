import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== RECENT POSITIONS IN DATABASE ===")
res = sb.table('positions').select('id,symbol,side,size,entry_price,current_price,realized_pnl,status,rule_code,opened_at').order('opened_at', desc=True).limit(15).execute()

for p in res.data:
    print(f"ID: {p.get('id')} | Symbol: {p.get('symbol')} | Side: {p.get('side')} | Size: {p.get('size')} | Entry: {p.get('entry_price')} | Realized PnL: {p.get('realized_pnl')} | Status: {p.get('status')} | Rule: {p.get('rule_code')} | Opened At: {p.get('opened_at')}")
