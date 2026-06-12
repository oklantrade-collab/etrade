import asyncio
import os
import sys
import pandas as pd
from datetime import datetime, timezone

# Ensure backend root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase
from app.execution.provider_factory import create_provider
from app.analysis.indicators_v2 import calculate_all_indicators
from app.analysis.fibonacci_bb import extract_fib_levels
from app.strategy.market_regime import classify_market_risk
from app.strategy.rule_engine import evaluate_all_rules, load_rules_to_memory
from app.core.memory_store import BOT_STATE

async def run_simulation():
    print("============================================================")
    print("SIMULACIÓN DE LAS ÚLTIMAS 8 HORAS - EVALUACIÓN DE TODAS LAS REGLAS")
    print("============================================================\n")
    
    sb = get_supabase()
    
    # Load rules and configs to memory
    load_rules_to_memory()
    
    # Sync config
    from app.workers.scheduler import sync_db_config_to_memory
    await sync_db_config_to_memory()
    
    provider = create_provider('crypto_futures')
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT']
    
    for symbol in symbols:
        print(f"--- Procesando {symbol} ---")
        # Fetch 200 candles to have enough history for indicators, then simulate the last 96 (8h)
        df_raw = await provider.get_ohlcv(symbol, '5m', limit=200)
        if df_raw is None or df_raw.empty:
            print(f"No se pudieron descargar datos para {symbol}\n")
            continue
            
        df = calculate_all_indicators(df_raw, BOT_STATE.config_cache)
        
        triggers = []
        
        # Simulate last 96 bars (8 hours)
        for i in range(len(df) - 96, len(df)):
            if i < 30: # Ensure we have enough bars for indicators
                continue
                
            bar_window = df.iloc[:i+1].copy()
            last_bar = bar_window.iloc[-1]
            bar_time = last_bar.name if hasattr(last_bar, 'name') else last_bar.get('open_time')
            
            # Format time
            if isinstance(bar_time, pd.Timestamp):
                time_str = bar_time.strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_str = str(bar_time)
                
            # Calculate local snap
            try:
                fib_levels = extract_fib_levels(bar_window)
                regime = classify_market_risk(bar_window)
            except Exception as e:
                continue
            
            # Evaluate rules
            match_long = evaluate_all_rules(bar_window, fib_levels, regime, direction='long')
            match_short = evaluate_all_rules(bar_window, fib_levels, regime, direction='short')
            
            for match in [match_long, match_short]:
                if match:
                    rule = match['rule']
                    triggers.append({
                        'time': time_str,
                        'price': last_bar['close'],
                        'rule_code': rule['rule_code'],
                        'direction': match['direction'],
                        'reason': match.get('reason') or rule.get('notes') or rule.get('description') or 'Matched standard rule conditions'
                    })
        
        if triggers:
            print(f"Se encontraron {len(triggers)} triggers en las últimas 8 horas:")
            for t in triggers:
                print(f"  [{t['time']}] {t['direction'].upper()} {t['rule_code']} a ${t['price']:.4f} | Razón: {t['reason']}")
        else:
            print("No se disparó ninguna regla en las últimas 8 horas.")
        print()

if __name__ == '__main__':
    asyncio.run(run_simulation())
