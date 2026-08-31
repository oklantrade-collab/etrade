import os
import dotenv
from supabase import create_client

root_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

res = sb.table('positions').select('*').in_('symbol', ['SOLUSDT', 'SOL/USDT']).order('opened_at', desc=True).limit(5).execute()
for p in (res.data or []):
    print(f"ID: {p.get('id')}\nSymbol: {p.get('symbol')}\nStatus: {p.get('status')}\nSide: {p.get('side')}\nEntry: {p.get('entry_price')}\nClosed Px: {p.get('current_price')}\nClose Reason: {p.get('close_reason')}\nOpened: {p.get('opened_at')}\nClosed: {p.get('closed_at')}\nRealized PnL: {p.get('realized_pnl')}\n---")
