import os
import dotenv
dotenv.load_dotenv(r'backend\.env')
from supabase import create_client
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])

res = sb.table('paper_trades').select('rule_code, total_pnl_usd').in_('rule_code', ['Dd11', 'Dd12']).execute()

trades = res.data
dd11_trades = [t for t in trades if t['rule_code'] == 'Dd11']
dd12_trades = [t for t in trades if t['rule_code'] == 'Dd12']

print(f'Dd11 (LONG) trades: {len(dd11_trades)}')
if dd11_trades:
    print(f'Dd11 PNL: {sum(t.get("total_pnl_usd", 0) for t in dd11_trades)}')

print(f'Dd12 (SHORT) trades: {len(dd12_trades)}')
if dd12_trades:
    print(f'Dd12 PNL: {sum(t.get("total_pnl_usd", 0) for t in dd12_trades)}')
