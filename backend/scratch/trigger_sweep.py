import sys
import os
import asyncio

# Add backend to path
sys.path.append(os.path.abspath('.'))

from app.workers.market_sweep import run_market_sweep

if __name__ == "__main__":
    print("Iniciando barrido manual del universo...")
    asyncio.run(run_market_sweep())
    print("Barrido completado.")
