import asyncio
import os
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.workers.scheduler import _process_symbol_15m, BOT_STATE
from app.execution.data_provider import BinanceCryptoProvider
from app.core.config import settings
from app.core.supabase_client import get_supabase

async def simulate_cycle():
    print("Simulando 15m cycle LOCALMENTE para poblar pilot_diagnostics...")
    
    # Init BOT_STATE
    BOT_STATE.config_cache = {
        "symbols_active": ["ADAUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "market_type": "futures",
        "paper_trading": True,
        "observe_only": True # NO TRADES
    }
    
    sb = get_supabase()
    provider = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    
    # Common state
    global_state = sb.table("bot_global_state").select("*").eq("id", 1).maybe_single().execute()
    gs_data = global_state.data or {}
    
    # Process ADA
    print("Processing ADAUSDT...")
    try:
        await _process_symbol_15m("ADAUSDT", provider, gs_data, sb)
        print("ADAUSDT processed.")
    except Exception as e:
        print(f"ADAUSDT failed: {e}")

    # Process BTC
    print("Processing BTCUSDT...")
    try:
        await _process_symbol_15m("BTCUSDT", provider, gs_data, sb)
        print("BTCUSDT processed.")
    except Exception as e:
        print(f"BTCUSDT failed: {e}")

    await provider.close()

if __name__ == "__main__":
    asyncio.run(simulate_cycle())
