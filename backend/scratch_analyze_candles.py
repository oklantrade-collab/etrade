import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def analyze_candles():
    sb = get_supabase()
    res = sb.table('market_candles')\
            .select('*')\
            .in_('symbol', ['GBPUSD', 'EURUSD'])\
            .order('open_time', desc=True)\
            .limit(50)\
            .execute()
            
    print("=== Last 50 Candles ===")
    if res.data:
        for c in res.data:
            print(f"Symbol: {c['symbol']} | TF: {c['timeframe']} | OpenTime: {c['open_time']} | Close: {c['close']}")
    else:
        print("No candles found")

if __name__ == "__main__":
    analyze_candles()
