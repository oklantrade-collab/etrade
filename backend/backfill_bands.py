import asyncio
import os
import sys
import pandas as pd
import numpy as np
from datetime import timezone
from dotenv import load_dotenv
from supabase import create_client

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.execution.data_provider import BinanceCryptoProvider
from app.analysis.fibonacci_bb import fibonacci_bollinger
from app.analysis.indicators_v2 import calculate_all_indicators

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)

async def backfill_bands():
    provider = BinanceCryptoProvider(
        os.getenv('BINANCE_API_KEY'),
        os.getenv('BINANCE_SECRET')
    )
    symbols  = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT']
    tfs      = ['5m', '15m', '30m', '4h', '1d']

    for symbol in symbols:
        for tf in tfs:
            try:
                # Descargar velas con indicadores
                df = await provider.get_ohlcv(symbol, tf, limit=300)
                if df is None or df.empty:
                    print(f'{symbol}/{tf}: No data')
                    continue
                
                # Calcular indicadores
                df = fibonacci_bollinger(df)
                df = calculate_all_indicators(df)

                # Upsert con bandas calculadas
                rows = []
                for _, row in df.iterrows():
                    # Asegurar TZ-aware para Postgres
                    open_time = row['open_time']
                    if open_time.tzinfo is None:
                        open_time = open_time.replace(tzinfo=timezone.utc)

                    item = {
                        'symbol':    symbol,
                        'exchange':  'binance',
                        'timeframe': tf,
                        'open_time': open_time.isoformat(),
                        'open':    float(row['open']),
                        'high':    float(row['high']),
                        'low':     float(row['low']),
                        'close':   float(row['close']),
                        'volume':  float(row['volume']),
                        'is_closed': True,
                    }
                    
                    # Bandas y otros indicadores con manejo de NaN
                    cols = [
                        'basis', 'upper_1', 'upper_2', 'upper_3', 'upper_4', 'upper_5', 'upper_6',
                        'lower_1', 'lower_2', 'lower_3', 'lower_4', 'lower_5', 'lower_6', 'sar'
                    ]
                    for col in cols:
                        val = row.get(col)
                        if pd.isna(val) or val is None:
                            item[col] = None
                        else:
                            item[col] = float(val)
                    
                    item['sar_trend'] = int(row.get('sar_trend', 0)) if pd.notna(row.get('sar_trend')) else 0
                    item['pinescript_signal'] = str(row.get('pinescript_signal', '')) if row.get('pinescript_signal') in ('Buy', 'Sell') else None
                    
                    rows.append(item)

                # Batch upsert
                for i in range(0, len(rows), 50):
                    batch = rows[i:i+50]
                    sb.table('market_candles').upsert(
                        batch,
                        on_conflict='symbol,exchange,timeframe,open_time'
                    ).execute()

                print(f'{symbol}/{tf}: {len(rows)} bandas calculadas y sincronizadas')
            except Exception as e:
                print(f'{symbol}/{tf}: FALLO - {e}')

    await provider.close()

if __name__ == "__main__":
    asyncio.run(backfill_bands())
