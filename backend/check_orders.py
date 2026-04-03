import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

res = sb.table('pending_orders').select('symbol, direction, timeframe, rule_code, limit_price, sizing_pct, status, created_at, expires_at').eq('status', 'pending').order('created_at', desc=True).limit(10).execute()
print(f"{'SYMBOL':<10} | {'DIR':<5} | {'TF':<3} | {'RULE':<5} | {'PRICE':<8} | {'SIZE':<4} | {'STATUS':<8} | {'CREATED'}")
print("-" * 80)
for r in res.data:
    price = round(float(r['limit_price']), 4) if r.get('limit_price') else 0
    print(f"{r.get('symbol', ''):<10} | {r.get('direction', ''):<5} | {r.get('timeframe', ''):<3} | {r.get('rule_code', ''):<5} | {price:<8} | {r.get('sizing_pct', ''):<4} | {r.get('status', ''):<8} | {r.get('created_at', '')}")

