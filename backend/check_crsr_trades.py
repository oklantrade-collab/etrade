import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_crsr_trades():
    sb = get_supabase()
    res = sb.table('trades_journal').select('*').eq('ticker', 'CRSR').order('exit_date', desc=True).limit(5).execute()
    if res.data:
        for r in res.data:
            print(f"[{r.get('exit_date')}] Exit Price: {r.get('exit_price')} - PNL: {r.get('pnl_usd')} - Reason: {r.get('exit_reason')} - Trade Type: {r.get('trade_type')}")
    else:
        print("No trades found in journal.")

if __name__ == "__main__":
    check_crsr_trades()
