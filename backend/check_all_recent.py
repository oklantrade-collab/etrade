
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

def check_all_recent():
    print("Checking ALL tickers in technical_scores sorted by timestamp...")
    res = sb.table('technical_scores').select('ticker, timestamp, technical_score').order('timestamp', desc=True).limit(50).execute()
    
    if res.data:
        for r in res.data:
            print(f"[{r['timestamp']}] {r['ticker']}: Score={r['technical_score']}")
    else:
        print("Empty table.")

if __name__ == "__main__":
    check_all_recent()
