import asyncio
import os
import sys
from datetime import datetime, timezone
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase
from app.execution.data_provider import BinanceCryptoProvider
from app.analysis.indicators_v2 import calculate_all_indicators
from app.strategy.strategy_engine import StrategyEngine

async def main():
    sb = get_supabase()
    engine = StrategyEngine(sb)
    await engine.load()
    
    provider = BinanceCryptoProvider(api_key='x', api_secret='x', market='futures')
    
    # fetch 5m
    df_5m = await provider.get_ohlcv("ADAUSDT", "5m", limit=300)
    df_5m = calculate_all_indicators(df_5m)
    
    print("Evaluating Aa21 on 5m timeframe since 09:10 UTC...")
    trades = []
    
    for i in range(100, len(df_5m)):
        bar = df_5m.iloc[i]
        time = bar.name
        # we evaluate all to be sure
        time_str = pd.to_datetime(time, unit='ms') if isinstance(time, (int, float)) else time
            
        # build context for rule engine
        # need context keys matching condition variables
        context = {}
        for col in df_5m.columns:
            context[col] = bar[col]
            
        context['price'] = bar['close']
        
        # evaluate
        results = engine.evaluate_all(context, 'long', 'scalping', '5m')
        
        for r in results:
            if r['rule_code'] == 'Aa21' and r['triggered']:
                print(f"[{time}] TRIGGERED Aa21 on 5m at price {bar['close']}! Score: {r['score']}")
                trades.append({
                    'time': time,
                    'price': bar['close']
                })
                
    if not trades:
        print("No trades triggered for Aa21 on 5m.")
        
    print("\nEvaluating Aa21 on 15m timeframe since 09:10 UTC...")
    df_15m = await provider.get_ohlcv("ADAUSDT", "15m", limit=150)
    df_15m = calculate_all_indicators(df_15m)
    trades_15m = []
    
    for i in range(50, len(df_15m)):
        bar = df_15m.iloc[i]
        time = bar.name
        time_str = pd.to_datetime(time, unit='ms') if isinstance(time, (int, float)) else time
            
        context = {}
        for col in df_15m.columns:
            context[col] = bar[col]
        context['price'] = bar['close']
        
        results = engine.evaluate_all(context, 'long', 'scalping', '15m')
        for r in results:
            if r['rule_code'] == 'Aa21' and r['triggered']:
                print(f"[{time}] TRIGGERED Aa21 on 15m at price {bar['close']}! Score: {r['score']}")
                trades_15m.append({
                    'time': time,
                    'price': bar['close']
                })
                
    if not trades_15m:
        print("No trades triggered for Aa21 on 15m.")

if __name__ == "__main__":
    asyncio.run(main())
