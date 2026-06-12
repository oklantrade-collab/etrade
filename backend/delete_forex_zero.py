import asyncio
from supabase import create_client
import os

supabase = create_client(
    os.getenv('SUPABASE_URL', 'https://dfrsccxkhicyhkprpsqt.supabase.co'),
    os.getenv('SUPABASE_SERVICE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRmcnNjY3hraGljeWhrcHJwc3F0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDUxNzQzNywiZXhwIjoyMDk2MDkzNDM3fQ.02nGn1J9wb8_K0_TAJ6uohWgNiUc_dQQ3tgE1xsgrmw')
)

res = supabase.table('forex_positions').select('*').eq('status', 'closed').execute()
for p in res.data:
    pnl = p.get('pnl_usd')
    if pnl == 0 or pnl == 0.0 or pnl == '0' or pnl == '0.00':
        print(f"Borrando forex_position {p['id']} - Symbol: {p['symbol']} - PNL: {pnl}")
        supabase.table('forex_positions').delete().eq('id', p['id']).execute()

res2 = supabase.table('paper_trades').select('*').execute()
for p in res2.data:
    pnl = p.get('total_pnl_usd')
    if pnl == 0 or pnl == 0.0 or pnl == '0' or pnl == '0.00':
        print(f"Borrando paper_trade {p['id']} - Symbol: {p['symbol']} - PNL: {pnl}")
        supabase.table('paper_trades').delete().eq('id', p['id']).execute()
