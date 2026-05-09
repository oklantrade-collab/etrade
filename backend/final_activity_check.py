from app.core.supabase_client import get_supabase

def final_check():
    sb = get_supabase()
    # Check both open and error recently updated
    res = sb.table('stocks_positions').select('ticker,status,updated_at,sl_close_reason').gte('updated_at', '2026-05-07T20:45:00').execute()
    print(f"Total rows updated since 20:45: {len(res.data)}")
    for p in res.data:
        print(f"{p.get('ticker')} | {p.get('status')} | {p.get('updated_at')} | {p.get('sl_close_reason')}")

if __name__ == "__main__":
    final_check()
