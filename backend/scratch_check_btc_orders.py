import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== RECENT BTCUSDT ORDERS ===")
try:
    res = sb.table('orders').select('*').eq('symbol', 'BTCUSDT').order('created_at', desc=True).limit(5).execute()
    for row in res.data:
        print(f"ID: {row.get('id')} | Created: {row.get('created_at')} | Status: {row.get('status')} | Side: {row.get('side')} | Quantity: {row.get('quantity')} | Entry: {row.get('entry_price')} | SL: {row.get('stop_loss_price')} | TP: {row.get('take_profit_price')}")
except Exception as e:
    print("Error querying orders:", e)
