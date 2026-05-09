from app.core.supabase_client import get_supabase
import json

def list_journal():
    sb = get_supabase()
    res = sb.table('trades_journal').select('*').order('exit_date', desc=True).limit(20).execute()
    print(f"Recently closed trades ({len(res.data)}):")
    for t in res.data:
        print(f"{t.get('ticker')} | {t.get('exit_date')} | PNL: {t.get('pnl_usd')} | Strategy: {t.get('trade_type')}")

if __name__ == "__main__":
    list_journal()
