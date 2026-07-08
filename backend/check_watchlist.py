import os
import sys
from datetime import date
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_watchlist():
    import io
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        
    sb = get_supabase()
    today = date.today().isoformat()
    print(f"Watchlist Daily for {today}:")
    try:
        res = sb.table('watchlist_daily')\
            .select('ticker, price, hard_filter_pass, pool_type, catalyst_score, quality_flag')\
            .eq('date', today)\
            .execute()
            
        if res.data:
            for idx, r in enumerate(res.data, 1):
                pool = r.get('pool_type') or ''
                print(f"#{idx:<2} | {r['ticker']:<5} | Price: ${r['price']:<6.2f} | HardFilterPass: {r['hard_filter_pass']} | Pool: {pool:<12} | CatalystScore: {r['catalyst_score']} | Quality: {r['quality_flag']}")
        else:
            print("No records found in watchlist_daily for today.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_watchlist()
