import asyncio
import os
import sys
from datetime import datetime

# Ajustar path
sys.path.append(os.getcwd())

from app.workers.stocks_scheduler import process_ticker, get_stocks_config, get_watchlist

async def main():
    print("=== FORZANDO ANALISIS TECNICO DE MADRUGADA ===")
    config = get_stocks_config()
    tickers = await get_watchlist(config)
    print(f"Detectados {len(tickers)} tickers en la lista de hoy.")
    
    for ticker in tickers:
        print(f"-> Analizando {ticker}...")
        try:
            await process_ticker(ticker, config)
        except Exception as e:
            print(f"Error en {ticker}: {e}")
            
    print("=== ANALISIS COMPLETADO ===")

if __name__ == "__main__":
    asyncio.run(main())
