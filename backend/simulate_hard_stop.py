import asyncio
import pandas as pd
from datetime import datetime, timezone
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase
from app.analysis.indicators_v2 import calculate_all_indicators

async def simulate():
    sb = get_supabase()
    
    # 1. Fetch candles from DB for XAUUSD 5m after entry time, plus some history for EMA200 calculation
    res = sb.table('market_candles').select('*').eq('symbol', 'XAUUSD').eq('timeframe', '5m').gte('open_time', '2026-07-15T00:00:00').order('open_time', desc=False).execute()
    candles = res.data
    
    if not candles:
        print("No candles found in DB for XAUUSD 5m.")
        return
        
    df = pd.DataFrame(candles)
    df['close'] = pd.to_numeric(df['close'])
    df['high'] = pd.to_numeric(df['high'])
    df['low'] = pd.to_numeric(df['low'])
    df['open'] = pd.to_numeric(df['open'])
    
    # Calculate EMA20, EMA50, EMA200
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # Calculate RSI 14
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    rs = ema_up / ema_down
    df['rsi'] = 100 - (100 / (1 + rs))
    
    entry_price = 4159.44
    entry_time = pd.to_datetime('2026-07-22T16:00:56Z')
    hard_stop_price = entry_price * 0.99  # 1% loss limit (Long)
    
    print(f"Entry Price: {entry_price}")
    print(f"Hard Stop Price (1% loss): {hard_stop_price}")
    print("-" * 70)
    
    hard_stop_hit = False
    erep_hit = False
    
    for _, row in df.iterrows():
        t = pd.to_datetime(row['open_time'])
        if t.tzinfo is None:
            t = t.tz_localize('UTC')
            
        if t < entry_time:
            continue
            
        close_price = row['close']
        ema20 = row['ema20']
        ema50 = row['ema50']
        ema200 = row['ema200']
        rsi = row['rsi']
        low_price = float(row['low'])
        
        # Check EREP conditions first (simulated)
        if rsi < 20 and not erep_hit and not hard_stop_hit:
            print(f"[{t}] >> EREP ACTIVATION CONDITION MET: RSI = {rsi:.2f} < 20")
            print(f"Price at EREP: {close_price:.2f}")
            erep_hit = True
            # In a real scenario, EREP would buy here, changing the entry price. 
            # We'll just note it and continue to see if Hard Stop would be hit.
            
        # Check Hard Stop conditions
        loss_pct = (entry_price - low_price) / entry_price * 100
        
        if loss_pct >= 1.0 and not hard_stop_hit:
            print(f"\n[{t}] Price reached {low_price:.2f} (Loss: -{loss_pct:.2f}% >= -1%).")
            print(f"Conditions: EMA20: {ema20:.2f} | EMA50: {ema50:.2f} | EMA200: {ema200:.2f}")
            
            # check the condition ema20 < ema50 < ema200
            if ema20 < ema50 and ema50 < ema200:
                print(">> ✅ HARD STOP EXECUTED: EMA20 < EMA50 < EMA200 logic MET!")
                print(f">> Posición cerrada en {low_price:.2f} limitando la pérdida al 1%.")
                hard_stop_hit = True
                break
            else:
                print(">> ❌ HARD STOP BLOCKED: Las EMAs no están en tendencia bajista total (EMA20 < EMA50 < EMA200 no se cumple).")
                print("   Se continuará aguantando la posición (EREP/SLV).")
                hard_stop_hit = True # just to stop printing it every minute
                
    if not hard_stop_hit and not erep_hit:
        print("Ni el Hard Stop ni el EREP se hubieran activado.")

if __name__ == '__main__':
    asyncio.run(simulate())
