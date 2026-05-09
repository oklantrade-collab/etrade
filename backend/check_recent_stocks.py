from app.core.supabase_client import get_supabase

def check_recent():
    sb = get_supabase()
    res = sb.table('stocks_positions').select('ticker,status,updated_at').gte('updated_at', '2026-05-07T00:00:00').execute()
    print("Recent Stocks Activity:")
    for p in res.data:
        print(f"{p.get('ticker')} | {p.get('status')} | {p.get('updated_at')}")

if __name__ == "__main__":
    check_recent()
