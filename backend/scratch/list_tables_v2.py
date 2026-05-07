from app.core.supabase_client import get_supabase

sb = get_supabase()
tables = ["forex_positions_history", "historical_trades", "trades_journal_forex"]

for t in tables:
    try:
        res = sb.table(t).select("*").limit(0).execute()
        print(f"Table exists: {t}")
    except Exception:
        print(f"Table does not exist: {t}")
