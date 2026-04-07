"""
Sincroniza datos técnicos frescos para AAPL en Supabase.
Garantiza que la prueba de Capa 5 tenga datos que leer.
"""
import asyncio
from app.workers.stocks_scheduler import process_ticker, get_stocks_config

async def sync():
    config = get_stocks_config()
    print("Sincronizando AAPL...")
    res = await process_ticker("AAPL", config)
    if res:
        print(f"AAPL OK: Score={res['technical_score']}")
    else:
        print("Fallo sincronización.")

if __name__ == "__main__":
    asyncio.run(sync())
