import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.workers.scheduler import cycle_15m, cycle_5m, load_config_to_memory, load_rules_to_memory, sync_db_config_to_memory
from app.core.memory_store import BOT_STATE

async def run_test():
    print("Simulando ciclo de 15m (Parallel)...")
    load_config_to_memory()
    load_rules_to_memory()
    await sync_db_config_to_memory()
    print(f"Config cache symbols_active: {BOT_STATE.config_cache.get('symbols_active')}")
    await cycle_15m()
    print("Simulando ciclo de 5m (Parallel)...")
    await cycle_5m()
    print("Test completado.")

if __name__ == "__main__":
    asyncio.run(run_test())
