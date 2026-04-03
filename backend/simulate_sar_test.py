from app.core.supabase_client import get_supabase
from app.workers.scheduler import cycle_15m, load_rules_to_memory, load_config_to_memory, warm_up
from app.execution.data_provider import BinanceCryptoProvider
from app.core.config import settings
from app.core.memory_store import BOT_STATE
import asyncio
from datetime import datetime, timezone

async def simulate_sar_change():
    sb = get_supabase()
    symbol = 'BTCUSDT'
    
    print(f"--- SIMULANDO CAMBIO DE FASE SAR PARA {symbol} ---")
    
    # 1. Forzar cambio a SHORT en la base de datos
    now_iso = datetime.now(timezone.utc).isoformat()
    sb.table('market_snapshot').update({
        'sar_trend_4h': -1,
        'sar_phase': 'short',
        'sar_phase_changed_at': now_iso
    }).eq('symbol', symbol).execute()
    
    print(f"Snapshot actualizado: SAR Phase -> SHORT, Changed At -> {now_iso}")

    # 2. Cargar estado inicial (warm_up) para que el bot sepa de la posición abierta
    load_config_to_memory()
    load_rules_to_memory()
    provider = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    await warm_up([symbol], ["15m", "4h"], provider)
    await provider.close()
    
    if symbol in BOT_STATE.positions:
        print(f"Posición encontrada en memoria: {BOT_STATE.positions[symbol]['side']}")
    else:
        print(f"ADVERTENCIA: No se encontró posición abierta para {symbol} en 'bot_state'")

    # 3. Ejecutar ciclo de 15m
    print("Ejecutando ciclo 15m...")
    await cycle_15m()
    
    # 4. Verificar resultados
    print("\n--- RESULTADOS ---")
    
    # Verificar en positions (Supabase)
    pos_res = sb.table('positions').select('status, close_reason').eq('symbol', 'BTC/USDT').execute()
    # Nota: El bot usa BTC/USDT en algunas tablas y BTCUSDT en otras.
    # En scheduler.py se usa symbol.replace('/', '') para market_snapshot pero a veces symbol con / para positions.
    # Vamos a probar ambos.
    if not pos_res.data:
        pos_res = sb.table('positions').select('status, close_reason').eq('symbol', 'BTCUSDT').execute()
    
    if pos_res.data:
        print(f"Status en 'positions': {pos_res.data[0]['status']}, Reason: {pos_res.data[0]['close_reason']}")
    else:
        print("No se encontró la posición en 'positions'.")

    # Verificar en paper_trades
    pt_res = sb.table('paper_trades').select('symbol, status, close_reason, total_pnl_usd').eq('symbol', 'BTC/USDT').order('closed_at', desc=True).limit(1).execute()
    if pt_res.data:
        print(f"Último paper_trade: {pt_res.data[0]['symbol']} {pt_res.data[0]['status']}, Reason: {pt_res.data[0]['close_reason']}, PnL: {pt_res.data[0]['total_pnl_usd']}")
    else:
        print("No se encontró registro en paper_trades.")

    # 5. RESTAURAR (Opcional, pero sugerido por el usuario)
    # Re-calcularemos el SAR real en el próximo ciclo normal, pero vamos a limpiar el flag
    sb.table('market_snapshot').update({
        'sar_trend_4h': 1,
        'sar_phase': 'long',
        'sar_phase_changed_at': None
    }).eq('symbol', symbol).execute()
    print("Snapshot restaurado a LONG (neutralizado).")

if __name__ == "__main__":
    asyncio.run(simulate_sar_change())
