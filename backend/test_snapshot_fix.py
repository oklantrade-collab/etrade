import asyncio
import pandas as pd
from app.execution.data_provider import BinanceCryptoProvider
from app.analysis.indicators_v2 import calculate_all_indicators
from app.workers.scheduler import write_market_snapshot
from app.core.supabase_client import get_supabase
from app.core.config import settings

async def manual_snapshot():
    print("Running manual snapshot for BTCUSDT...")
    prov = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    sb = get_supabase()
    
    df = await prov.get_ohlcv('BTC/USDT', '15m', limit=300)
    df = calculate_all_indicators(df, {})
    
    await write_market_snapshot(
        'BTCUSDT', df, {'category': 'diesgo_bajo', 'risk_score': 10}, 
        {'detected': False}, 0.55, sb
    )
    
    print("Snapshot written. Verifying...")
    res = sb.table('market_snapshot').select('symbol, price, upper_1, upper_2, upper_3, upper_4, upper_5, upper_6, updated_at').eq('symbol', 'BTCUSDT').execute()
    print(res.data)
    
    await prov.close()

if __name__ == "__main__":
    asyncio.run(manual_snapshot())
