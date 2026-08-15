import os
import sys
import asyncio
# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

from app.halcon_centinela.centinela_monitor import CentinelaMonitor

async def run_evaluation():
    print("Iniciando evaluación HALCON CENTINELA en tiempo real (Mock Data)...\n")
    # Initialize monitor with no execution service for dry run
    monitor = CentinelaMonitor(execution_service=None, market_type='forex')
    
    symbols = ['EURUSD', 'BTCUSD']
    for symbol in symbols:
        print(f"=========================================")
        print(f"Evaluando activo: {symbol}")
        print(f"=========================================")
        try:
            position_data = {
                'id': f'mock-pos-{symbol}',
                'symbol': symbol,
                'entry_price': 1.0500 if symbol == 'EURUSD' else 60000.0,
                'current_price': 1.0510 if symbol == 'EURUSD' else 61000.0,
                'volume': 1000,
                'direction': 'long',
                'side': 'long',
                'entry_profile': 'TENDENCIA_SOSTENIDA'
            }
            # Gather market data and evaluate via the monitor's logic
            market_data = monitor._gather_market_data(symbol)
            result = monitor.halcon.evaluate(position=position_data, market_data=market_data)
            
            print(f"-> Score Final: {result.score_final}")
            print(f"-> Semáforo: {result.semaforo}")
            print(f"-> Decisión Sugerida: {result.decision}")
            print(f"-> Razón: {result.reason}")
            print(f"-> Sub-scores:")
            if hasattr(result, 'detail') and 'sub_scores' in result.detail:
                for k, v in result.detail['sub_scores'].items():
                    print(f"   {k}: {v}")
            print("\n")
        except Exception as e:
            print(f"Error evaluando {symbol}: {e}\n")

if __name__ == '__main__':
    asyncio.run(run_evaluation())
