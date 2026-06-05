import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.execution.provider_factory import create_provider
from app.analysis.indicators_v2 import calculate_all_indicators
from app.analysis.fibonacci_bb import extract_fib_levels
from app.strategy.market_regime import classify_market_risk
from app.strategy.rule_engine import evaluate_all_rules, DEFAULT_RULES

async def simulate_8h():
    print("--- Simulacion 8 horas (96 velas de 5m) ---")
    provider_crypto = create_provider('crypto_futures')
    
    symbols_crypto = ['BTCUSDT', 'ETHUSDT']
    symbols_forex = ['EURUSD', 'XAUUSD', 'USDJPY']
    
    results = []
    
    # Crypto
    for sym in symbols_crypto:
        print(f"Descargando {sym}...")
        df = await provider_crypto.get_ohlcv(sym, '5m', limit=200)
        if df is None or df.empty:
            continue
        
        df = calculate_all_indicators(df, {})
        
        # Simular ultimas 96 velas (8 horas)
        triggers = {'Aa21': 0, 'Bb21': 0, 'AaHot': 0, 'BbHot': 0, 'AaRebound_5m': 0, 'BbRebound_5m': 0}
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
                
            match = evaluate_all_rules(bar_window, fib_levels, regime, rules=DEFAULT_RULES)
            if match:
                rc = match['rule']['rule_code']
                if rc in triggers:
                    triggers[rc] += 1
                    trades += 1
                    # Pseudo PnL based on volatility
                    total_pnl += (last['atr'] if last.get('atr') else 0) * (0.5 if rc.startswith('A') else 0.5)

        print(f"[{sym}] Trades simulados en ultimas 8h: {trades}")
        for k, v in triggers.items():
            if v > 0: print(f"  - {k}: {v} triggers")
        print(f"  - PnL estimado: +{total_pnl:.2f} USD")
        
    # Forex
    provider_forex = create_provider('forex_futures')
    connected = await provider_forex.connect()
    if connected:
        for sym in symbols_forex:
            print(f"Descargando {sym}...")
            df = await provider_forex.get_ohlcv(sym, '5m', limit=200)
            if df is None or df.empty:
                continue
            
            # fill bollinger columns
            df['upper_5'] = df['close'].rolling(20).mean() + 2.5 * df['close'].rolling(20).std()
            df['lower_5'] = df['close'].rolling(20).mean() - 2.5 * df['close'].rolling(20).std()
            
            df = calculate_all_indicators(df, {})
            
            triggers = {'Aa21': 0, 'Bb21': 0, 'AaHot': 0, 'BbHot': 0, 'AaRebound_5m': 0, 'BbRebound_5m': 0}
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
                    
                match = evaluate_all_rules(bar_window, fib_levels, regime, rules=DEFAULT_RULES)
                if match:
                    rc = match['rule']['rule_code']
                    if rc in triggers:
                        triggers[rc] += 1
                        trades += 1
                        total_pnl += (last['atr'] if last.get('atr') else 0) * 10
            
            print(f"[{sym}] Trades simulados en ultimas 8h: {trades}")
            for k, v in triggers.items():
                if v > 0: print(f"  - {k}: {v} triggers")
            print(f"  - PnL estimado (pips/ticks): +{total_pnl:.2f}")

    await provider_forex.disconnect()

if __name__ == '__main__':
    asyncio.run(simulate_8h())
