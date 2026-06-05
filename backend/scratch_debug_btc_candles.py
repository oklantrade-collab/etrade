import asyncio
import os
import sys
import pandas as pd

# Add root directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.core.supabase_client import get_supabase

async def check_candles():
    sb = get_supabase()
    try:
        print("=== BTCUSDT CANDLES 15M (31/05/2026 22:00 UTC ONWARDS) ===")
        # Query candles for BTCUSDT, timeframe 15m, ordered by open_time
        res = sb.table('market_candles')\
            .select('*')\
            .eq('symbol', 'BTCUSDT')\
            .eq('timeframe', '15m')\
            .gte('open_time', '2026-05-31T22:00:00')\
            .lte('open_time', '2026-06-01T06:00:00')\
            .order('open_time', desc=False)\
            .execute()
            
        candles = res.data or []
        if not candles:
            print("No candles found in database.")
            return
            
        df = pd.DataFrame(candles)
        df['open_time_utc'] = pd.to_datetime(df['open_time'])
        df = df.sort_values('open_time_utc').reset_index(drop=True)
        
        # Calculate EMA3, EMA9, EMA20, EMA50
        df['ema3'] = df['close'].ewm(span=3, adjust=False).mean()
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        for idx, row in df.iterrows():
            print(f"Time (UTC): {row['open_time']} | O: {row['open']:.2f} | H: {row['high']:.2f} | L: {row['low']:.2f} | C: {row['close']:.2f} | EMA3: {row['ema3']:.2f} | EMA9: {row['ema9']:.2f} | EMA20: {row['ema20']:.2f}")
            
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(check_candles())
