import asyncio
import os
import sys
import pandas as pd

# Add root directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.core.supabase_client import get_supabase

async def check_confluence():
    sb = get_supabase()
    try:
        print("=== EVALUACIÓN DETALLADA DE CONFLUENCIA (31/05/2026 22:00 ONWARDS) ===")
        # Fetch 200 candles before 22:00 to have accurate EMA50 and EMA200
        res = sb.table('market_candles')\
            .select('*')\
            .eq('symbol', 'BTCUSDT')\
            .eq('timeframe', '15m')\
            .gte('open_time', '2026-05-29T00:00:00')\
            .lte('open_time', '2026-06-01T06:00:00')\
            .order('open_time', desc=False)\
            .execute()
            
        candles = res.data or []
        df = pd.DataFrame(candles)
        df['open_time_utc'] = pd.to_datetime(df['open_time'])
        df = df.sort_values('open_time_utc').reset_index(drop=True)
        
        # Calculate EMAs
        df['ema3'] = df['close'].ewm(span=3, adjust=False).mean()
        df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # Filter from 31/05/2026 22:00 UTC onwards
        df_filtered = df[df['open_time_utc'] >= '2026-05-31 22:00:00'].copy()
        
        for idx, row in df_filtered.iterrows():
            ema3 = row['ema3']
            ema9 = row['ema9']
            ema20 = row['ema20']
            ema50 = row['ema50']
            ema200 = row['ema200']
            
            c3_9_20 = (ema3 > ema9) and (ema9 >= ema20)
            c50_200 = ema50 > ema200
            confluence = c3_9_20 and c50_200
            
            print(f"Time (UTC): {row['open_time']} | C: {row['close']:.2f} | EMA3: {ema3:.2f} | EMA9: {ema9:.2f} | EMA20: {ema20:.2f} | EMA50: {ema50:.2f} | EMA200: {ema200:.2f} | EMA3>9>=20: {c3_9_20} | EMA50>200: {c50_200} | CONFLUENCE: {confluence}")
            
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(check_confluence())
