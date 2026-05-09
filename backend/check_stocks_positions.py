from app.core.supabase_client import get_supabase

def check_stocks():
    sb = get_supabase()
    res = sb.table('stocks_positions').select('ticker,status,updated_at').order('updated_at', desc=True).limit(20).execute()
    print("Recent Stocks Positions:")
    for p in res.data:
        print(f"{p.get('ticker')} | {p.get('status')} | {p.get('updated_at')}")

if __name__ == "__main__":
    check_stocks()
