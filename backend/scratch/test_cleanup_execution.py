import sys
import os
import asyncio
sys.path.append('c:/Fuentes/eTrade/backend')

from app.workers.data_cleanup import cleanup_database

async def test_clean():
    print("=== PROBANDO EJECUCIÓN SILENCIOSA DE DB_CLEANUP ===")
    res = await cleanup_database()
    print("Resultado del mantenimiento de DB:")
    for k, v in res.items():
        print(f"  - {k}: {v}")

if __name__ == "__main__":
    asyncio.run(test_clean())
