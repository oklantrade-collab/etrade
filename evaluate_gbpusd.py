import os
import sys
import asyncio
from pprint import pprint
# Ensure backend directory is in path
sys.path.insert(0, '/home/etrade/etrade/backend')
from dotenv import load_dotenv
load_dotenv('/home/etrade/etrade/backend/.env')

from app.halcon_centinela.centinela_monitor import CentinelaMonitor

def run_evaluation():
    print("=========================================")
    print(" HALCON CENTINELA - REALTIME EVALUATION  ")
    print("=========================================")
    
    # Initialize monitor with no execution service for dry run
    monitor = CentinelaMonitor(execution_service=None, market_type='forex')
    
    symbol = 'GBPUSD'
    
    # Live position from DB that we fetched
    position_data = {
        'id': '14fb9636-98b0-4b4b-bf7c-db899a4e81aa',
        'symbol': symbol,
        'entry_price': 1.34847,
        'current_price': 1.34544,
        'volume': 1000,
        'direction': 'short',
        'side': 'short',
        'entry_profile': 'TENDENCIA_SOSTENIDA',
        'pips_pnl': 11.1
    }
    
    try:
        market_data = monitor._gather_market_data(symbol)
        
        # Ensure data exists
        if market_data['df_1m'] is None or market_data['df_1m'].empty:
            print("No real-time market data found for GBPUSD in memory store. Cannot evaluate accurately.")
            return

        result = monitor.halcon.evaluate(position=position_data, market_data=market_data)
        
        print(f"\n--- POSITION INFO ---")
        print(f"Symbol: {symbol} | Side: {position_data['side']} | Entry: {position_data['entry_price']} | Current: {position_data['current_price']} | Pips PnL: {position_data['pips_pnl']}")
        
        print(f"\n--- HALCON RESULT ---")
        print(f"-> Score Final: {result.score_final}")
        print(f"-> Semáforo: {result.semaforo}")
        print(f"-> Decisión Sugerida: {result.decision}")
        print(f"-> Razón: {result.detail.get('reason', 'N/A')}")
        
        print(f"\n--- SUB SCORES ---")
        if hasattr(result, 'detail') and 'sub_scores' in result.detail:
            for k, v in result.detail['sub_scores'].items():
                print(f"   {k}: {v}")
                
        print("\n=========================================\n")
    except Exception as e:
        print(f"Error evaluando {symbol}: {e}")

if __name__ == '__main__':
    run_evaluation()
