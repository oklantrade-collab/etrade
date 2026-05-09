from app.core.supabase_client import get_supabase
from datetime import datetime, timezone

def check_today_stocks():
    sb = get_supabase()
    # Today starts at midnight Lima/NYC (approx UTC-5)
    today_start = "2026-05-07T00:00:00"
    res = sb.table('stocks_positions').select('*').gte('first_buy_at', today_start).execute()
    print(f"Today's Stocks Positions ({len(res.data)}):")
    for p in res.data:
        print(f"{p.get('ticker')} | {p.get('status')} | {p.get('first_buy_at')}")

if __name__ == "__main__":
    check_today_stocks()
