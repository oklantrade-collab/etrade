import os
import sys
import dotenv
from supabase import create_client

root_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

print("=== RECENT CLOSED POSITIONS (last 10) ===")
res = sb.table('positions').select('*').order('closed_at', desc=True).limit(10).execute()
for r in res.data:
    print(f"ID={r.get('id')} | Sym={r.get('symbol')} | Side={r.get('side')} | Opened={r.get('opened_at')} | Closed={r.get('closed_at')} | Entry={r.get('entry_price')} | ClosePx={r.get('current_price')} | Reason={r.get('close_reason')} | Strategy={r.get('rule_code')} | PnL={r.get('realized_pnl')}")
