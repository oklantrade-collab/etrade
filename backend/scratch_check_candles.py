import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from datetime import datetime, timezone

def check_candles():
    sb = get_supabase()
    res = sb.table('market_candles')\
            .select('*')\
            .in_('symbol', ['GBPUSD', 'EURUSD'])\
            .gte('open_time', '2026-06-01T04:40:00+00:00')\
            .lte('open_time', '2026-06-01T05:00:00+00:00')\
            .execute()
            
    print("=== Candles around 04:49 ===")
    if res.data:
        for c in res.data:
            print(f"Symbol: {c['symbol']} | TF: {c['timeframe']} | OpenTime: {c['open_time']} | Close: {c['close']}")
    else:
        print("No candles found")

if __name__ == "__main__":
    check_candles()
