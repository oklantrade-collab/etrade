"""
eTrade v4 — Startup & Warm-up Manager
Reconstructs bot memory from Supabase and Binance.
Ensures the system is ready before the first cycle.
"""
import asyncio
from datetime import datetime, timezone
import pandas as pd

from app.core.logger import log_info, log_error
from app.core.supabase_client import get_supabase
from app.core.memory_store import BOT_STATE, update_memory_df
from app.execution.data_provider import BinanceCryptoProvider
from app.analysis.indicators_v2 import calculate_all_indicators # Need to ensure this exists

MODULE = "startup"

async def verify_rules_integrity(sb) -> bool:
    """
    Verifica que las 13 reglas están correctamente
    cargadas en Supabase al iniciar el worker.
    """
    try:
        res = sb.table('trading_rules')\
            .select('id, rule_code')\
            .gte('id', 1001)\
            .lte('id', 1013)\
            .eq('enabled', True)\
            .execute()

        count = len(res.data)
        if count != 13:
            log_error('STARTUP',
                f'Integridad de reglas FALLIDA: '
                f'{count}/13 reglas encontradas. '
                f'Ejecutar seed de trading_rules.')
            return False

        log_info('STARTUP',
            f'Integridad de reglas OK: 13/13 reglas activas')
        return True

    except Exception as e:
        log_error('STARTUP',
            f'Error verificando reglas: {e}')
        return False

async def warm_up(symbols: list[str], timeframes: list[str], provider: BinanceCryptoProvider):
    """
    1. Recover state from Supabase (WARM data from bot_state table)
    2. Reconstruct indicators from Binance (HOT data)
    """
    log_info(MODULE, f"Initiating v4 Warm-up for {len(symbols)} symbols...")
    start_time = datetime.now()
    
    sb = get_supabase()
    
    # --- PHASE 1: Recover Business State (WARM) ---
    try:
        # Load Open Positions from bot_state
        res_pos = sb.table("bot_state").select("*").eq("is_open", True).execute()
        for p in res_pos.data:
            # We reconstruct the Position object (or dict) in MEMORY_STORE
            BOT_STATE.positions[p['symbol']] = p
            
        # Load Global State (Circuit Breakers)
        res_global = sb.table("bot_global_state").select("*").eq("id", 1).execute()
        if res_global.data:
            BOT_STATE.global_state = res_global.data[0]
            
        log_info(MODULE, f"Phase 1 Complete: {len(BOT_STATE.positions)} positions recovered from 'bot_state'.")
    except Exception as e:
        log_error(MODULE, f"Error recovering state from bot_state: {e}")

    # --- PHASE 2: Reconstruct Indicators (HOT) ---
    tasks = []
    # Ensure current config is loaded for indicator calculations
    # ... logic for config load ...

    for symbol in symbols:
        for tf in timeframes:
            tasks.append(_warm_up_symbol_tf(symbol, tf, provider))
    
    await asyncio.gather(*tasks)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    log_info(MODULE, f"Phase 2 Complete: HOT indicators reconstructed in {elapsed:.2f}s.")

async def _warm_up_symbol_tf(symbol: str, tf: str, provider: BinanceCryptoProvider):
    try:
        # Fetch data for calculation
        df = await provider.get_ohlcv(symbol, tf, limit=300)
        # Use the definitive v4 pipeline
        from app.analysis.indicators_v2 import calculate_all_indicators
        df = calculate_all_indicators(df, BOT_STATE.config_cache)
        update_memory_df(symbol, tf, df)
    except Exception as e:
        log_error(MODULE, f"Error warming up {symbol} {tf}: {e}")

if __name__ == "__main__":
    # Test shortcut
    import os
    from app.core.config import settings
    
    p = BinanceCryptoProvider(settings.BINANCE_API_KEY, settings.BINANCE_SECRET)
    asyncio.run(warm_up(["BTC/USDT"], ["15m", "4h"], p))
