from app.core.supabase_client import get_supabase

def check_db():
    try:
        sb = get_supabase()
        res = sb.table("stocks_positions").select("ticker, status").eq("status", "open").execute()
        print(f"OPEN POSITIONS: {len(res.data or [])}")
        for p in (res.data or []):
            print(f" - {p['ticker']}")
            
        res_closed = sb.table("stocks_positions").select("ticker, status").eq("status", "closed").limit(5).execute()
        print(f"CLOSED POSITIONS (Last 5): {len(res_closed.data or [])}")
        for p in (res_closed.data or []):
            print(f" - {p['ticker']}")
            
    except Exception as e:
        print(f"DB ERROR: {e}")

if __name__ == "__main__":
    check_db()
