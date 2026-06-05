import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.execution.provider_factory import create_provider
from app.analysis.indicators_v2 import calculate_all_indicators

async def simulate_new_rule():
    print("--- Simulacion de Nueva Regla: 8 horas (96 velas de 5m) ---", flush=True)
    provider_crypto = create_provider('crypto_futures')
    symbols_crypto = ['BTCUSDT', 'ETHUSDT']
    
    for sym in symbols_crypto:
        print(f"Descargando {sym}...", flush=True)
        try:
            df = await provider_crypto.get_ohlcv(sym, '5m', limit=200)
            if df is None or df.empty:
                print(f"No hay datos para {sym}", flush=True)
                continue
            
            # Use calculate_all_indicators to populate ema1, ema2, ema3, atr, etc.
            df = calculate_all_indicators(df, {})
            
            trades = 0
            total_pnl = 0.0
            
            # Analyze last 96 candles
            start_idx = len(df) - 96
            for i in range(start_idx, len(df)):
                if i < 1: continue
                
                # Current row
                row = df.iloc[i]
                # Previous row
                prev = df.iloc[i-1]
                
                ema3_val = row['ema1'] # EMA 3
                ema9_val = row['ema2'] # EMA 9
                ema20_val = row['ema3'] # EMA 20
                
                prev_ema3_val = prev['ema1']
                prev_ema9_val = prev['ema2']
                
                # Condition: Primer cruce del EMA3 > EMA9
                cruce_up = (ema3_val > ema9_val) and (prev_ema3_val <= prev_ema9_val)
                
                # And (EMA9 > EMA20 or EMA3 > EMA20)
                sec_cond = (ema9_val > ema20_val) or (ema3_val > ema20_val)
                
                if cruce_up and sec_cond:
                    trades += 1
                    # Rough PnL estimation: standard TP logic uses 1.5 ATR for scalp
                    atr = row.get('atr', row['close'] * 0.01)
                    total_pnl += atr * 1.5 # projecting a win of 1.5 ATR
            
            print(f"[{sym}] Trades abiertos: {trades}", flush=True)
            print(f"  - PnL proyectado (basado en +1.5 ATR): +{total_pnl:.2f} USD", flush=True)
            
        except Exception as e:
            print(f"Error procesando {sym}: {e}", flush=True)

if __name__ == '__main__':
    asyncio.run(simulate_new_rule())
