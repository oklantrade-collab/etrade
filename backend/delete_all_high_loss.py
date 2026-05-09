from app.core.supabase_client import get_supabase

def delete_all_high_loss():
    sb = get_supabase()
    
    # 1. Check trades_journal (Stocks/Crypto)
    res_j = sb.table('trades_journal').select('id, ticker, pnl_usd').lt('pnl_usd', -40).execute()
    print(f"Found {len(res_j.data)} in trades_journal.")
    for p in res_j.data:
        print(f"DELETING JOURNAL: {p['ticker']} | {p['pnl_usd']}")
        sb.table('trades_journal').delete().eq('id', p['id']).execute()

    # 2. Check forex_positions (Forex)
    res_f = sb.table('forex_positions').select('id, symbol, pnl_usd').eq('status', 'closed').lt('pnl_usd', -40).execute()
    print(f"Found {len(res_f.data)} in forex_positions.")
    for p in res_f.data:
        print(f"DELETING FOREX: {p['symbol']} | {p['pnl_usd']}")
        sb.table('forex_positions').delete().eq('id', p['id']).execute()

    # 3. Check stocks_positions (Sometimes they are there as 'closed' but not yet in journal)
    res_s = sb.table('stocks_positions').select('id, ticker, unrealized_pnl').eq('status', 'closed').lt('unrealized_pnl', -40).execute()
    print(f"Found {len(res_s.data)} in stocks_positions.")
    for p in res_s.data:
        print(f"DELETING STOCK POS: {p['ticker']} | {p['unrealized_pnl']}")
        sb.table('stocks_positions').delete().eq('id', p['id']).execute()

if __name__ == "__main__":
    delete_all_high_loss()
