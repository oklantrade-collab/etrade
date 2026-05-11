import os
import json
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('backend/.env')

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

res = sb.table('forex_positions').select('*').eq('symbol', 'USDJPY').order('opened_at', desc=True).limit(20).execute()
for p in res.data:
    print(f"ID: {p['id']} | Rule: {p['rule_code']} | Entry: {p['entry_price']} | Exit: {p['current_price']} | Result: ${p['pnl_usd']} | Pips: {p['pnl_pips']} | Reason: {p['close_reason']}")
