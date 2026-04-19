
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
    print(f"--- TECHNICAL SCORES DISTRIBUTION {today} ---")
    
    # Check signals from today
    res = sb.table('stocks_signals').select('ticker, technical_score, pro_score, created_at')\
        .gte('created_at', today).order('technical_score', desc=True).execute()
    
    if res.data:
        print(f"Found {len(res.data)} signals today.")
        scores = [r['technical_score'] for r in res.data]
        from collections import Counter
        dist = Counter(scores)
        print("Score Distribution:")
        for s in sorted(dist.keys(), reverse=True):
            print(f"- Score {s}: {dist[s]} tickers")
        
        print("\nTop 10 Tickers by Tech Score:")
        for r in res.data[:10]:
            print(f"- {r['ticker']}: Tech={r['technical_score']}, Pro={r['pro_score']}, Time={r['created_at']}")
    else:
        print("No signals found for today in stocks_signals.")

if __name__ == "__main__":
    check_today()
