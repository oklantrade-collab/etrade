import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.execution.provider_factory import create_provider
from app.analysis.indicators_v2 import calculate_all_indicators
from app.analysis.fibonacci_bb import extract_fib_levels
from app.strategy.market_regime import classify_market_risk
from app.strategy.rule_engine import evaluate_all_rules, DEFAULT_RULES

async def simulate_crypto():
    print("--- Simulacion 8 horas (96 velas de 5m) ---", flush=True)
    provider_crypto = create_provider('crypto_futures')
    
    symbols_crypto = ['BTCUSDT', 'ETHUSDT']
    
    # Crypto
    for sym in symbols_crypto:
        print(f"Descargando {sym}...", flush=True)
        try:
            df = await provider_crypto.get_ohlcv(sym, '5m', limit=200)
            if df is None or df.empty:
                print(f"No hay datos para {sym}", flush=True)
                continue
            
            df = calculate_all_indicators(df, {})
            
            # Simular ultimas 96 velas (8 horas)
            triggers = {'Aa21': 0, 'Bb21': 0, 'AaHot': 0, 'BbHot': 0}
            total_pnl = 0.0
            trades = 0
            
            for i in range(len(df)-96, len(df)):
                if i < 100: continue
                bar_window = df.iloc[: i + 1].copy()
                last = bar_window.iloc[-1]
                try:
                    fib_levels = extract_fib_levels(bar_window)
                    regime = classify_market_risk(bar_window)
                except:
                    continue
                    
                match_long = evaluate_all_rules(bar_window, fib_levels, regime, direction='long', rules=DEFAULT_RULES)
                match_short = evaluate_all_rules(bar_window, fib_levels, regime, direction='short', rules=DEFAULT_RULES)
                
                for match in [match_long, match_short]:
                    if match:
                        rc = match['rule']['rule_code']
                        if rc in triggers:
                            triggers[rc] += 1
                            trades += 1
                            total_pnl += (last['atr'] if last.get('atr') else 0) * (1.5 if rc.startswith('A') else 1.5)

            print(f"[{sym}] Trades simulados en ultimas 8h: {trades}", flush=True)
            for k, v in triggers.items():
                if v > 0: print(f"  - {k}: {v} triggers", flush=True)
            print(f"  - PnL proyectado basado en ATR: +{total_pnl:.2f} USD", flush=True)
        except Exception as e:
            print(f"Error procesando {sym}: {e}", flush=True)

if __name__ == '__main__':
    asyncio.run(simulate_crypto())
