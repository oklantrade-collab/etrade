from app.core.supabase_client import get_supabase

def check_open():
    sb = get_supabase()
    tickers = ['ABTS', 'ATXG', 'CGCT', 'SPPL', 'WKHS']
    res = sb.table('stocks_positions').select('ticker,first_buy_at').in_('ticker', tickers).eq('status', 'open').execute()
    print("Open positions times:")
    for p in res.data:
        print(f"{p.get('ticker')} | {p.get('first_buy_at')}")

if __name__ == "__main__":
    check_open()
