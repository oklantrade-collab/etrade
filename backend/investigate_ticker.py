
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

def check_ticker(ticker):
    print(f"--- INVESTIGATING {ticker} ---")
    
    # Check technical_scores
    res_ts = sb.table('technical_scores').select('*').eq('ticker', ticker).execute()
    if res_ts.data:
        ts = res_ts.data[0]
        print(f"Technical Score: {ts['technical_score']}, MTF: {ts['mtf_confirmed']}")
        sj = ts['signals_json']
        print(f"Pro Score: {sj.get('pro_score')}")
        print(f"AI Rationale: {sj.get('ai_rationale')}")
        print(f"Movement: {sj.get('movement_15m')}")
        print(f"Pine Signal: {sj.get('t01_confirmed')} (T01)")
    else:
        print(f"No technical score found for {ticker}")

    # Check system_logs for the ticker
    print(f"\nRecent logs for {ticker}:")
    res_logs = sb.table('system_logs').select('*').ilike('message', f'%{ticker}%').order('created_at', desc=True).limit(20).execute()
    if res_logs.data:
        for l in res_logs.data:
            print(f"[{l['created_at']}] {l['message']}")
    else:
        print(f"No logs found for {ticker}")

if __name__ == "__main__":
    for t in ["NVTS", "TRVI", "BORR"]:
        check_ticker(t)
        print("\n" + "="*50 + "\n")
