import asyncio
import os
import sys

# Agregar path del backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.stocks.universe_builder import UniverseBuilder
from app.workers.stocks_scheduler import process_ticker, get_stocks_config
from app.core.logger import log_info

async def test_cycle_v2():
    print("\n" + "="*50)
    print(" PRUEBA DE CICLO V2: Market Cap > $500M | Price < $200")
    print("="*50)

    # 1. Obtener Configuración
    config = get_stocks_config()
    max_price = float(config.get("scanner_max_price", 200.0))
    min_cap = int(config.get("scanner_min_market_cap", 500_000_000))
    print(f"\n[CONFIG] Precio Máximo: ${max_price} | Market Cap Mínimo: ${min_cap/1e6:.0f}M")

    # 2. Capa 0: Descubrimiento Filtrado (IB Scanner)
    print("\n[CAPA 0] Ejecutando Universe Builder con filtros de calidad...")
    builder = UniverseBuilder()
    candidates = await builder.build_daily_watchlist(max_price=max_price, min_market_cap=min_cap)
    
    if not candidates:
        print("\n[INFO] No se encontraron candidatos con estos filtros. Intentando sin Market Cap solo para prueba...")
        candidates = await builder.build_daily_watchlist(max_price=max_price, min_market_cap=0)

    if not candidates:
        print("\n[ERROR] Sin candidatos tras varios intentos.")
        return

    print(f"\n[OK] Se obtuvieron mejores candidatos. Analizando los top 3...")
    
    # 3. Capas 1-2: Cálculo con yfinance
    test_tickers = [c["ticker"] for c in candidates[:3]]

    for ticker in test_tickers:
        print(f"\n--- Analizando {ticker} ---")
        result = await process_ticker(ticker, config)
        if result:
            print(f"  > Precio: ${result['price']:.2f}")
            print(f"  > Score Técnico: {result['technical_score']}")
            print(f"  > RVOL: {result['rvol']:.2f}")
            print(f"  > Estado: {'APROBADO ✅' if result['acceptable'] else 'Esperando Señal ⏳'}")
        else:
            print(f"  > [ERROR] Error en cálculo de indicadores para {ticker}")

    print("\n" + "="*50)
    print(" PRUEBA COMPLETADA")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(test_cycle_v2())
