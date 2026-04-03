import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

sb = get_supabase()

allowed = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]

for table in ["market_candles", "technical_indicators", "volume_spikes", "trading_signals"]:
    print(f"Cleaning {table}")
    res = sb.table(table).select("symbol").execute()
    symbols = set(r["symbol"] for r in res.data)
    for s in symbols:
        if s not in allowed:
            print(f"Deleting {s} from {table}")
            sb.table(table).delete().eq("symbol", s).execute()

print("Done.")
