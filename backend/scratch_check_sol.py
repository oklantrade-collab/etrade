import os
import dotenv
from supabase import create_client

root_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

res = sb.table('positions').select('*').in_('symbol', ['SOLUSDT', 'SOL/USDT']).execute()
print(f"Total SOL positions: {len(res.data or [])}")
for p in (res.data or []):
    print(f"ID: {p.get('id')} | Symbol: {p.get('symbol')} | Status: {p.get('status')} | Side: {p.get('side')} | Mode: {p.get('mode')} | is_paper: {p.get('is_paper')} | Opened: {p.get('opened_at')}")
