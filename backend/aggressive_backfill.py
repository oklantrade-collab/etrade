import asyncio
import os
import sys
import pandas as pd
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.execution.data_provider import BinanceCryptoProvider
from app.analysis.indicators_v2 import calculate_all_indicators
from app.core.config import settings
from app.core.supabase_client import get_supabase

async def aggressive_backfill():
    sb = get_supabase()
    provider = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]
    
    timeframes = ['15m', '1h', '4h', '1d']
    
    for symbol in symbols:
        for tf in timeframes:
            print(f"[{symbol}] Aggressive backfill for {tf}...")
            # Fetch 1000 candles to ensure indicators have enough lookback
            df_raw = await provider.get_ohlcv(symbol, tf, limit=1000)
            if df_raw is None or df_raw.empty:
                continue
                
            df = calculate_all_indicators(df_raw, {})
            
            # Prepare rows, ensuring NO 0.0 values for indicators
            rows = []
            # We take all 1000 candles
            for _, r in df.iterrows():
                ot = r['open_time']
                if ot.tzinfo is None:
                    ot = ot.replace(tzinfo=timezone.utc)
                
                rows.append({
                    "symbol": symbol,
                    "exchange": "binance",
                    "timeframe": tf,
                    "open_time": ot.isoformat(),
                    "open": float(r['open']),
                    "high": float(r['high']),
                    "low": float(r['low']),
                    "close": float(r['close']),
                    "volume": float(r['volume']),
                    "is_closed": True,
                    "basis": float(r['basis']) if pd.notna(r.get('basis')) and r['basis'] != 0 else None,
                    "upper_6": float(r['upper_6']) if pd.notna(r.get('upper_6')) and r['upper_6'] != 0 else None,
                    "lower_6": float(r['lower_6']) if pd.notna(r.get('lower_6')) and r['lower_6'] != 0 else None,
                    "sar": float(r['sar']) if pd.notna(r.get('sar')) and r['sar'] != 0 else None,
                    "sar_trend": int(r['sar_trend']) if pd.notna(r.get('sar_trend')) else None
                })
            
            # Upsert in chunks of 100 to avoid payload issues
            for i in range(0, len(rows), 100):
                chunk = rows[i:i+100]
                sb.table('market_candles').upsert(chunk, on_conflict="symbol,exchange,timeframe,open_time").execute()
            
            print(f"[{symbol}] {tf}: Upserted {len(rows)} rows.")
            
    await provider.close()

if __name__ == "__main__":
    asyncio.run(aggressive_backfill())
