import os
import sys
import pandas as pd
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from app.strategy.erep_manager import detect_p2_entry_signal

def analyze():
    sb = get_supabase()
    # Get candles
    print("Fetching candles...")
    c5 = sb.table('candles_5m').select('*').eq('symbol', 'ADAUSDT').gte('timestamp', '2026-07-19T04:00:00Z').lte('timestamp', '2026-07-19T06:00:00Z').order('timestamp', desc=False).execute()
    df_5m = pd.DataFrame(c5.data)
    
    if len(df_5m) > 0:
        for index, row in df_5m.iterrows():
            if '04:40' in row['timestamp'] or '04:45' in row['timestamp'] or '04:50' in row['timestamp'] or '05:30' in row['timestamp'] or '05:35' in row['timestamp'] or '05:40' in row['timestamp']:
                print(f"5m Candle {row['timestamp']}: O={row.get('open')} H={row.get('high')} L={row.get('low')} C={row.get('close')}")
    else:
        print("No 5m candles found.")
        
    print("Done")

if __name__ == '__main__':
    analyze()
