from app.core.supabase_client import get_supabase

def check_14():
    sb = get_supabase()
    tickers = ['ASAN', 'GOVX', 'OPCH', 'VLN', 'ATXG', 'ABTS', 'WKHS', 'ATLX', 'FIP', 'SPPL', 'CGCT', 'HTZ', 'ONEG', 'HLN']
    res = sb.table('stocks_positions').select('ticker,status,updated_at').in_('ticker', tickers).execute()
    print("Status of 14 tickers:")
    for p in res.data:
        print(f"{p.get('ticker')} | {p.get('status')} | {p.get('updated_at')}")

if __name__ == "__main__":
    check_14()
