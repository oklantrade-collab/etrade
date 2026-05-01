import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase
from app.workers.stocks_scheduler import run_stocks_tp_cycle

async def force_tp_check():
    print("🚀 Forzando ciclo de TP para verificar FIP...")
    await run_stocks_tp_cycle()
    print("✅ Ciclo completado.")

if __name__ == "__main__":
    asyncio.run(force_tp_check())
