import os, sys
sys.path.append(os.path.abspath('backend'))
from app.core.supabase_client import get_supabase
sb = get_supabase()

print('=== TRADES_JOURNAL >= 2026-10-21 ===')
tj = sb.table('trades_journal').select('*').gte('entry_date', '2026-10-21T00:00:00Z').order('entry_date').execute().data or []
for t in tj:
    print(f"{t.get('ticker')} | Entry: {t.get('entry_date')} @ {t.get('entry_price')} | Exit: {t.get('exit_date')} @ {t.get('exit_price')} | Shares: {t.get('shares')} | PnL: ${t.get('pnl_usd')} ({t.get('pnl_pct')}%) | Reason: {t.get('exit_reason')}")
