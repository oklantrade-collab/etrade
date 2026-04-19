
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
    
    # Check technical_scores from today
    # Since we delete and insert, just getting everything is basically the latest state
    res = sb.table('technical_scores').select('ticker, technical_score, mtf_confirmed, timestamp').order('technical_score', desc=True).execute()
    
    if res.data:
        print(f"Found {len(res.data)} scores in table.")
        for r in res.data[:20]:
            print(f"- {r['ticker']}: Score={r['technical_score']}, MTF={r['mtf_confirmed']}, Time={r['timestamp']}")
    else:
        print("No scores found in technical_scores table.")

if __name__ == "__main__":
    check_today()
