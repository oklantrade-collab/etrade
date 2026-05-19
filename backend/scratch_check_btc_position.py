import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== RECENT BTCUSDT POSITIONS ===")
try:
    res = sb.table('positions').select('*').eq('symbol', 'BTCUSDT').order('opened_at', desc=True).limit(5).execute()
    for row in res.data:
        print(f"ID: {row.get('id')} | Opened: {row.get('opened_at')} | Status: {row.get('status')} | Side: {row.get('side')} | Size: {row.get('size')} | Entry: {row.get('entry_price')} | PNL: {row.get('realized_pnl')} | Reason: {row.get('close_reason')}")
except Exception as e:
    print("Error querying positions:", e)
