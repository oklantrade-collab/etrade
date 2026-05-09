from app.core.supabase_client import get_supabase

def delete_high_loss_trades():
    sb = get_supabase()
    # Find trades with loss > $40
    res = sb.table('trades_journal').select('id, ticker, pnl_usd, exit_date').lt('pnl_usd', -40).execute()
    
    print(f"Found {len(res.data)} trades with loss > $40:")
    for p in res.data:
        print(f"ID: {p['id']} | Ticker: {p['ticker']} | PnL: {p['pnl_usd']} | Date: {p['exit_date']}")
    
    if res.data:
        ids = [p['id'] for p in res.data]
        # Delete from trades_journal
        del_res = sb.table('trades_journal').delete().in_('id', ids).execute()
        print(f"Successfully deleted {len(ids)} trades from trades_journal.")
    else:
        print("No trades found to delete.")

if __name__ == "__main__":
    delete_high_loss_trades()
