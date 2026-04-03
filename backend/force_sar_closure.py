from app.core.supabase_client import get_supabase
from app.workers.scheduler import cycle_15m, load_rules_to_memory, load_config_to_memory, warm_up
from app.execution.data_provider import BinanceCryptoProvider
from app.core.config import settings
from app.core.memory_store import BOT_STATE, MEMORY_STORE
import asyncio
from datetime import datetime, timezone

async def simulate_force_closure():
    sb = get_supabase()
    symbol = 'BTCUSDT'
    
    print(f"--- SIMULANDO CIERRE POR SAR PARA {symbol} ---")
    
    # 1. Preparar memoria
    load_config_to_memory()
    load_rules_to_memory()
    provider = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    await warm_up([symbol], ["15m", "4h"], provider)
    await provider.close()
    
    # 2. Mockear una posición LONG en memoria (aunque no exista realmente en Supabase)
    # pero para que funcione el closure, debe existir en Supabase o el provider fallará.
    # El usuario tiene una posición abierta en la dashboard, así que usaremos esa.
    BOT_STATE.positions[symbol] = {
        'symbol': symbol,
        'side': 'long',
        'entry_price': 70934.0,
        'id': 'test_btc_id'
    }
    
    # 3. Mockear el cambio de SAR a SHORT en memoria
    now_iso = datetime.now(timezone.utc).isoformat()
    MEMORY_STORE[symbol]['sar'] = {
        'phase': 'short',
        'value_4h': 70000.0,
        'trend_4h': -1,
        'changed_at': now_iso # Esto activará el if sar_changed_at en el scheduler
    }
    
    print(f"Memoria mockeada: SAR -> SHORT, Changed At -> {now_iso}, POS -> LONG")

    # 4. Ejecutar el ciclo de 15m.
    # IMPORTANTE: El ciclo de 15m llama a write_market_snapshot al INICIO, lo cual sobreescribirá 
    # mi mock de memoria si no tengo cuidado.
    # Pero el scheduler llama a write_market_snapshot PRIMERO.
    # Así que el mock debe ser DESPUÉS de write_market_snapshot o dentro del ciclo.
    
    # Vamos a llamar directamente a _process_symbol_15m
    from app.workers.scheduler import _process_symbol_15m
    from app.execution.data_provider import PaperTradingProvider

    provider = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    paper_provider = PaperTradingProvider(provider)
    
    # Mockear datos globales
    gs_data = {'circuit_breaker_active': False}
    
    print("Ejecutando _process_symbol_15m...")
    await _process_symbol_15m(symbol, paper_provider, gs_data, sb)
    
    await provider.close()
    
    print("\n--- VERIFICACIÓN FINAL ---")
    # Verificar si se cerró en paper_trades
    pt_res = sb.table('paper_trades').select('symbol, status, close_reason').eq('symbol', 'BTC/USDT').order('closed_at', desc=True).limit(1).execute()
    if pt_res.data:
        print(f"Último paper_trade: {pt_res.data[0]['symbol']}, Reason: {pt_res.data[0]['close_reason']}")
    else:
        print("No se encontró el paper_trade.")

if __name__ == "__main__":
    asyncio.run(simulate_force_closure())
