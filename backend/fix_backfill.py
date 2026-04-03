import asyncio
import os
import sys
from dotenv import load_dotenv
from supabase import create_client
import pandas as pd

# Path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.execution.data_provider import BinanceCryptoProvider
from datetime import datetime, timezone

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)

async def backfill():
    # Use the definitive provider
    from app.core.config import settings
    provider = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret, market='futures')
    symbols  = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT']
    tfs      = ['15m', '30m', '1h', '4h', '1d']

    for symbol in symbols:
        # Standardize to slash format for API compatibility
        sym_slash = f"{symbol[:-4]}/USDT" if symbol.endswith('USDT') else symbol
        
        for tf in tfs:
            print(f"Fetching {symbol} {tf}...")
            df = await provider.get_ohlcv(symbol, tf, limit=300)
            if df is None or df.empty:
                print(f'{symbol}/{tf}: sin datos')
                continue

            rows = []
            for idx, row in df.iterrows():
                # Ensure TZ-awareness (Critical Fix)
                ot = row['open_time']
                if ot.tzinfo is None:
                    ot = ot.replace(tzinfo=timezone.utc)
                
                rows.append({
                    'symbol':    sym_slash, # Using slash format as expected by API
                    'exchange':  'binance',
                    'timeframe': tf,
                    'open_time': ot.isoformat(),
                    'open':      float(row['open']),
                    'high':      float(row['high']),
                    'low':       float(row['low']),
                    'close':     float(row['close']),
                    'volume':    float(row['volume']),
                    'is_closed': True
                })

            # Insertar en lotes de 50
            for i in range(0, len(rows), 50):
                batch = rows[i:i+50]
                try:
                    sb.table('market_candles')\
                      .upsert(
                          batch,
                          on_conflict='symbol,exchange,timeframe,open_time'
                      ).execute()
                except Exception as e:
                    print(f"Error in batch {i}: {e}")

            print(f'{symbol}/{tf}: {len(rows)} velas insertadas (en formato slash)')

    await provider.close()

if __name__ == "__main__":
    asyncio.run(backfill())
