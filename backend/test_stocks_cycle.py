import asyncio
import os
import sys

# Agregar path del backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.stocks.universe_builder import UniverseBuilder
from app.workers.stocks_scheduler import process_ticker, get_stocks_config
from app.core.logger import log_info

async def test_cycle():
    print("\n" + "="*50)
    print(" INICIANDO PRUEBA DE FLUJO COMPLETO (Capa 0 + Capas 1-2)")
    print("="*50)

    # 1. Obtener Configuración
    config = get_stocks_config()
    max_price = float(config.get("scanner_max_price", 200.0))
    print(f"\n[CONFIG] Precio Máximo del Scanner: ${max_price}")

    # 2. Capa 0: Descubrimiento de Tickers (IB Scanner / Fallback)
    print("\n[CAPA 0] Ejecutando Universe Builder...")
    builder = UniverseBuilder()
    candidates = await builder.build_daily_watchlist(max_price=max_price)
    
    if not candidates:
        print("\n[ERROR] No se encontraron candidatos. ¿Está abierto TWS/IB Gateway?")
        return

    print(f"\n[RESULTADO] Se encontraron {len(candidates)} candidatos.")
    
    # 3. Analizar los top 3 candidatos con yfinance
    test_tickers = [c["ticker"] for c in candidates[:3]]
    print(f"\n[ANÁLISIS] Procesando los top 3: {test_tickers}...")

    for ticker in test_tickers:
        print(f"\n--- Analizando {ticker} ---")
        result = await process_ticker(ticker, config)
        if result:
            print(f"  > Precio: ${result['price']:.2f}")
            print(f"  > Score Técnico: {result['technical_score']}")
            print(f"  > RVOL: {result['rvol']:.2f}")
            print(f"  > Estado: {'APROBADO ✅' if result['acceptable'] else 'Rechazado ❌'}")
        else:
            print(f"  > [ERROR] No se pudo obtener data para {ticker}")

    print("\n" + "="*50)
    print(" PRUEBA COMPLETADA")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(test_cycle())
