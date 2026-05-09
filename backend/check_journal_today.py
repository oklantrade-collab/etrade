from app.core.supabase_client import get_supabase
from datetime import datetime, timezone

def check_journal():
    sb = get_supabase()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    # Usar exit_date que es la columna real en trades_journal
    res = sb.table('trades_journal').select('*').gte('exit_date', f'{today}T00:00:00').execute()
    print(f"Total trades in journal today: {len(res.data)}")
    for t in res.data:
        print(f"Ticker: {t.get('ticker')} | Exit Date: {t.get('exit_date')} | PNL: {t.get('pnl_usd')} | Reason: {t.get('exit_reason')}")

if __name__ == "__main__":
    check_journal()
