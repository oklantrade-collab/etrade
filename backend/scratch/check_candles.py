import os
import sys
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from app.core.supabase_client import get_supabase

def check_candles():
    sb = get_supabase()
    res = sb.table('market_candles')\
        .select('*')\
        .eq('symbol', 'BTCUSDT')\
        .eq('timeframe', '15m')\
        .gte('open_time', '2026-06-01T00:30:00+00:00')\
        .lte('open_time', '2026-06-01T02:30:00+00:00')\
        .order('open_time', desc=False)\
        .execute()
    
    df = pd.DataFrame(res.data or [])
    if not df.empty:
        print("BTCUSDT 15m Candles:")
        for idx, row in df.iterrows():
            # Convert UTC open_time to local time (UTC-5)
            utc_time = datetime.fromisoformat(row['open_time'].replace('Z', '+00:00'))
            local_time = utc_time.astimezone(timezone(timedelta(hours=-5)))
            print(f"Local Time: {local_time.strftime('%Y-%m-%d %H:%M:%S')} | Open: {row['open']} | High: {row['high']} | Low: {row['low']} | Close: {row['close']}")

if __name__ == "__main__":
    from datetime import datetime, timezone, timedelta
    check_candles()
