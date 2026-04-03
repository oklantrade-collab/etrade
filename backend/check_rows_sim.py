import asyncio
import os
import sys
import pandas as pd

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.execution.data_provider import BinanceCryptoProvider
from app.analysis.indicators_v2 import calculate_all_indicators
from app.core.config import settings

async def check_rows():
    provider = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    df_raw = await provider.get_ohlcv('BTCUSDT', '4h', limit=500)
    
    # Simulate BOT_STATE.config_cache being empty (default case)
    df = calculate_all_indicators(df_raw, {})
    
    # Simulate rows creation from upsert_candles_to_db
    sub_df = df.tail(300)
    rows = []
    for _, r in sub_df.iterrows():
        rows.append({
            "open_time": r['open_time'].isoformat(),
            "basis": float(r.get('basis', 0) or 0) if pd.notna(r.get('basis')) else None,
            "upper_6": float(r.get('upper_6', 0) or 0) if pd.notna(r.get('upper_6')) else None
        })
    
    # Check the first few rows (which correspond to indices 1, 2, 3... in DB order)
    # Actually DB index 1 is row 498 in the 500-bar DF?
    # No, DB order is DESC. Index 0 is row 499. Index 1 is row 498.
    print(f"Total rows in upsert list: {len(rows)}")
    print("\nLATEST row in upsert list (should be index 0 in DB):")
    print(rows[-1]) 
    
    print("\nRow at index -2 in upsert list (should be index 1 in DB):")
    print(rows[-2])

    print("\nRow at index -100 in upsert list (should be index 99 in DB):")
    print(rows[-100])
    
    await provider.close()

if __name__ == "__main__":
    asyncio.run(check_rows())
