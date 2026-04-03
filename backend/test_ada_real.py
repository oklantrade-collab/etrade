import asyncio
import os
from dotenv import load_dotenv
from supabase import create_client
from app.analysis.swing_detector import (
    calculate_fall_maturity,
    SWING_CONFIG
)
from app.core.supabase_client import get_supabase
load_dotenv('c:/Fuentes/eTrade/backend/.env')

async def main():
    sb = get_supabase()
    # Mocking fetching from db directly because memory_store is empty locally
    # Or fetch from binance:
    from app.core.providers.binance_crypto import BinanceCryptoProvider
    import app.core.config as config
    provider = BinanceCryptoProvider(config.BINANCE_API_KEY, config.BINANCE_SECRET)
    
    for tf in ['15m', '4h']:
        df = await provider.fetch_ohlcv('ADAUSDT', tf, limit=100)
        from app.analysis.indicators_v2 import add_indicators_v2
        df = add_indicators_v2(df)
        
        cfg  = SWING_CONFIG[tf]
        result = calculate_fall_maturity(
            df             = df,
            direction      = 'long',
            min_bands      = cfg['min_bands'],
            min_basis_dist = cfg['min_basis_dist'],
            lookback       = cfg['lookback']
        )
        print(f'ADA {tf}:')
        print(f'  is_mature:     {result["is_mature"]}')
        print(f'  bands:         {result.get("bands_perforated")}')
        print(f'  basis_dist:    {result.get("basis_dist_pct")}%')
        print(f'  momentum_decr: {result.get("momentum_decreasing")}')
        print(f'  reason:        {result["reason"]}')
        print()

asyncio.run(main())
