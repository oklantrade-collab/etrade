import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.workers.data_cleanup import cleanup_database

async def main():
    print("Iniciando purga de la base de datos...")
    results = await cleanup_database()
    print("Purga finalizada. Resultados:")
    for key, value in results.items():
        print(f" - {key}: {value}")

if __name__ == "__main__":
    asyncio.run(main())
