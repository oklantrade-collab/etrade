import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta
from app.core.supabase_client import get_supabase
from app.data.yfinance_provider import YFinanceProvider

async def debug_ada():
    supabase = get_supabase()
    symbol = "ADA/USDT"
    
    # We want to check what happened around 12:45 UTC (07:45 AM EST)
    # We need to build the snapshot data as it was at 12:45 UTC.
    
    # Let's get the crypto snapshot first to see if ADAUSDT is there
    snap_res = supabase.table("market_snapshot").select("*").eq("symbol", symbol).execute()
    snap = snap_res.data[0] if snap_res.data else {}
    
    if not snap:
        print("No snapshot for ADA/USDT")
        return
        
    print(f"Snapshot loaded for {symbol}")
    
    # Let's load the rules
    rules_res = supabase.table("trading_rules").select("*").in_("rule_code", ["Aa21", "AaHot"]).execute()
    rules = rules_res.data
    
    if not rules:
        print("Rules Aa21, AaHot not found")
        return
        
    for rule in rules:
        print(f"\nEvaluating Rule: {rule['rule_code']}")
        print(f"Conditions: {rule.get('conditions', {})}")
        
        # We can evaluate manually to see what failed
        conds = rule.get('conditions', {})
        
        # 1. MTF score check
        mtf_min = float(conds.get('mtf_score', {}).get('min', -99))
        mtf_val = float(snap.get('mtf_score') or 0)
        print(f"MTF: {mtf_val} (Required min: {mtf_min}) -> {mtf_val >= mtf_min}")
        
        # 2. ADX check
        adx_min = float(conds.get('adx', {}).get('min', -99))
        adx_val = float(snap.get('adx') or 0)
        print(f"ADX: {adx_val} (Required min: {adx_min}) -> {adx_val >= adx_min}")
        
        # 3. EMA Cross check
        ema_cross = conds.get('ema3_cross_ema9_up')
        if ema_cross is not None:
            ema3 = float(snap.get('ema_3') or 0)
            ema9 = float(snap.get('ema_9') or 0)
            print(f"EMA3={ema3}, EMA9={ema9}, cross up required={ema_cross}")
            
        # 4. Fib check
        fib = conds.get('fibonacci_zone', {})
        fib_val = int(snap.get('fibonacci_zone', snap.get('fib_zone_15m', 0)))
        fib_max = int(fib.get('max', 99))
        fib_min = int(fib.get('min', -99))
        print(f"Fib Zone: {fib_val} (Required: {fib_min} to {fib_max}) -> {fib_min <= fib_val <= fib_max}")
        
        # 5. Price position
        price_pos = conds.get('price_position')
        if price_pos:
            price = float(snap.get('price') or 0)
            ema20 = float(snap.get('ema_20') or snap.get('ema20') or 0)
            ema50 = float(snap.get('ema_50') or snap.get('ema50') or 0)
            
            if price_pos == 'above_ema20':
                print(f"Price > EMA20: {price} > {ema20} -> {price > ema20}")
            elif price_pos == 'above_ema50':
                print(f"Price > EMA50: {price} > {ema50} -> {price > ema50}")
                
        # 6. BB Width
        bb = conds.get('bb_width_expanding')
        if bb is not None:
            bb_exp = bool(snap.get('bb_expanding', False))
            print(f"BB Expanding: {bb_exp} (Required: {bb}) -> {bb_exp == bb}")
            
        # 7. RVOL
        rvol = conds.get('rvol', {})
        rvol_min = float(rvol.get('min', 0))
        rvol_val = float(snap.get('rvol', 1.0))
        print(f"RVOL: {rvol_val} (Required min: {rvol_min}) -> {rvol_val >= rvol_min}")

if __name__ == "__main__":
    asyncio.run(debug_ada())
