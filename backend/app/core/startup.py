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
        # Load Open Positions from 'positions' table (v4 standard)
        res_pos = sb.table("positions").select("*").eq("status", "open").execute()
        for p in res_pos.data:
            # Key by pos_id to support multiple positions per symbol
            BOT_STATE.positions[p.get('id', p['symbol'])] = p
            
        # Load Global State (Circuit Breakers)
        res_global = sb.table("bot_global_state").select("*").eq("id", 1).execute()
        if res_global.data:
            BOT_STATE.global_state = res_global.data[0]
            
        log_info(MODULE, f"Phase 1 Complete: {len(BOT_STATE.positions)} positions recovered from 'positions' table.")
    except Exception as e:
        log_error(MODULE, f"Error recovering state from positions table: {e}")

    # --- PHASE 2: Reconstruct Indicators (HOT) ---
    tasks = []
    # Ensure current config is loaded for indicator calculations
    # ... logic for config load ...

    sem = asyncio.Semaphore(1)  # Límite estricto secuencial para evitar baneos en testnet

    async def _bounded_warmup(sym: str, timeframe: str):
        async with sem:
            await _warm_up_symbol_tf(sym, timeframe, provider)
            await asyncio.sleep(1.0)  # Delay agresivo de 1 segundo entre cada petición

    for symbol in symbols:
        for tf in timeframes:
            tasks.append(_bounded_warmup(symbol, tf))
    
    # gather_with_concurrency
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Verificar si hubo excepciones importantes
    banned = False
    for res in results:
        if isinstance(res, Exception):
            if "banned" in str(res).lower() or "IP_BANNED" in str(res):
                banned = True
            else:
                log_error(MODULE, f"Error en warmup (excepción capturada): {res}")
                
    if banned:
        log_error(MODULE, f"Startup warmup abortado: La IP está baneada en Binance hasta {BinanceCryptoProvider._ban_until_ts}.")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    log_info(MODULE, f"Phase 2 Complete: HOT indicators reconstructed in {elapsed:.2f}s.")

async def _warm_up_symbol_tf(symbol: str, tf: str, provider: BinanceCryptoProvider):
    try:
        if BinanceCryptoProvider.is_banned():
            raise Exception("IP_BANNED")
            
        # Fetch data for calculation
        df = await provider.get_ohlcv(symbol, tf, limit=300)
        # Use the definitive v4 pipeline
        from app.analysis.indicators_v2 import calculate_all_indicators
        df = calculate_all_indicators(df, BOT_STATE.config_cache)
        update_memory_df(symbol, tf, df)
        
        # Rehidratar caché en memoria para validación de seguridad y motor de estrategia
        if tf == '15m' and not df.empty:
            from app.core.memory_store import MARKET_SNAPSHOT_CACHE
            last_row = df.iloc[-1]
            MARKET_SNAPSHOT_CACHE.setdefault(symbol, {}).update({
                'price': float(last_row['close']),
                'ema_3': float(last_row.get('ema1', 0) if last_row.get('ema1') is not None else 0),
                'ema_9': float(last_row.get('ema2', 0) if last_row.get('ema2') is not None else 0),
                'ema_20': float(last_row.get('ema3', 0) if last_row.get('ema3') is not None else 0),
                'ema_50': float(last_row.get('ema4', 0) if last_row.get('ema4') is not None else 0),
                'rsi_14': float(last_row.get('rsi1', 0) if last_row.get('rsi1') is not None else 0),
                'atr': float(last_row.get('atr', 0) if last_row.get('atr') is not None else 0),
                'adx': float(last_row.get('adx', 0) if last_row.get('adx') is not None else 0),
                'macd_histogram': float(last_row.get('macd_hist', 0) if last_row.get('macd_hist') is not None else 0),
                'updated_at': datetime.now(timezone.utc).isoformat()
            })
            
    except Exception as e:
        if "banned" in str(e).lower() or "ip_banned" in str(e).lower():
            raise e
        log_error(MODULE, f"Error warming up {symbol} {tf}: {e}")

if __name__ == "__main__":
    # Test shortcut
    import os
    from app.core.config import settings
    
    p = BinanceCryptoProvider(settings.BINANCE_API_KEY, settings.BINANCE_SECRET)
    asyncio.run(warm_up(["BTC/USDT"], ["15m", "4h"], p))
