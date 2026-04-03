from app.core.supabase_client import get_supabase
from datetime import datetime
import pytz

def backfill():
    sb = get_supabase()
    # 1. Get recent paper_trades with None rule_code
    res = sb.table('paper_trades').select('id, symbol, closed_at').is_('rule_code', 'null').limit(50).execute()
    trades = res.data or []
    
    if not trades:
        print("No trades to backfill.")
        return

    print(f"Found {len(trades)} trades to fix.")
    
    for t in trades:
        # Try to find a rule_code for this symbol from the 'orders' table around the same time
        # or just the latest one for that symbol that is 'open' or was recently closed.
        symbol = t['symbol']
        
        # Look for orders for this symbol
        ord_res = sb.table('orders').select('rule_code').eq('symbol', symbol).not_.is_('rule_code', 'null').order('created_at', desc=True).limit(1).execute()
        if ord_res.data:
            rule = ord_res.data[0]['rule_code']
            sb.table('paper_trades').update({'rule_code': rule}).eq('id', t['id']).execute()
            print(f"Fixed {t['id']} [{symbol}] -> {rule}")

if __name__ == "__main__":
    backfill()
