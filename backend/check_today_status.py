
import os
import sys
from datetime import date
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set UTF-8 encoding for stdout
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.core.supabase_client import get_supabase

sb = get_supabase()

def check_today():
    today = date.today().isoformat()
    print(f"--- STATUS REPORT {today} ---")
    
    # 1. Watchlist Daily
    res_wl = sb.table('watchlist_daily').select('*').eq('date', today).execute()
    print(f"Universe Builder: {len(res_wl.data)} tickers found today.")

    # 2. Tech Scores (from stocks_signals or wherever they are stored)
    # Based on stocks_scheduler.py: upsert_technical_score(ticker, ind_15m, base_score, is_acceptable, pro_score)
    # Let's check stocks_signals table
    print("\nRecent Technical Scores (last 20 signals):")
    try:
        res_sig = sb.table('stocks_signals').select('ticker, technical_score, pro_score, last_scan_time')\
            .order('created_at', desc=True).limit(20).execute()
        if res_sig.data:
            for s in res_sig.data:
                print(f"- {s['ticker']}: Tech={s['technical_score']}, Pro={s['pro_score']}, Time={s['last_scan_time']}")
        else:
            print("No signals found in stocks_signals table.")
    except Exception as e:
        print(f"Error checking signals: {e}")

    # 3. Rules Engine Check
    print("\nChecking Rule Engine Configuration (stocks_config):")
    try:
        res_cfg = sb.table('stocks_config').select('*').execute()
        for c in res_cfg.data:
            print(f"- {c['key']}: {c['value']}")
    except Exception as e:
        print(f"Error checking config: {e}")

    # 4. Any errors?
    print("\nRecent Errors in logs:")
    res_err = sb.table('system_logs').select('*')\
        .eq('level', 'ERROR')\
        .order('created_at', desc=True).limit(10).execute()
    if res_err.data:
        for e in res_err.data:
            print(f"[{e['created_at']}] {e['module']} | {e['message']}")
    else:
        print("No errors found today.")

if __name__ == "__main__":
    check_today()
