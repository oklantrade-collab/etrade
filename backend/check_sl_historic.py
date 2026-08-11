import os
import sys
import pandas as pd
import yfinance as yf
from datetime import timedelta, datetime
from dateutil.parser import parse
from dotenv import load_dotenv

# Load env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from app.core.supabase_client import get_supabase

def calc_ema(df, period, col='Close'):
    return df[col].ewm(span=period, adjust=False).mean()

def main():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('close_reason', 'sl_hit_fx_hard').execute()
    
    positions = res.data
    total = len(positions)
    print(f"Total casos cerrados por 'sl_hit_fx_hard': {total}")
    
    if total == 0:
        return
        
    saved_count = 0
    
    for p in positions:
        symbol = p['symbol']
        side = p['side']
        closed_at_str = p['closed_at']
        if not closed_at_str:
            continue
            
        closed_at = parse(closed_at_str)
        # We need historical data up to closed_at
        # To get 15m candles, yfinance needs start/end
        
        start_dt = closed_at - timedelta(days=2)
        end_dt = closed_at + timedelta(days=1)
        
        # map symbol to yf format, e.g. XAUUSD -> GC=F or XAUUSD=X, EURUSD -> EURUSD=X
        yf_sym = symbol + '=X'
        if symbol == 'XAUUSD':
            yf_sym = 'GC=F'
            
        try:
            df = yf.download(yf_sym, start=start_dt.strftime('%Y-%m-%d'), end=end_dt.strftime('%Y-%m-%d'), interval='15m', progress=False)
            if df.empty:
                print(f"Could not fetch data for {yf_sym}")
                continue
                
            # Filter up to closed_at
            # Make df timezone aware or closed_at timezone naive
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC')
            if closed_at.tzinfo is None:
                closed_at = closed_at.replace(tzinfo=df.index.tz)
                
            df = df[df.index <= closed_at]
            if df.empty:
                continue
                
            df['EMA3'] = calc_ema(df, 3)
            df['EMA9'] = calc_ema(df, 9)
            
            last_row = df.iloc[-1]
            ema3 = last_row['EMA3']
            ema9 = last_row['EMA9']
            
            # extract scalar if it's a pandas series
            if isinstance(ema3, pd.Series):
                ema3 = ema3.iloc[0]
            if isinstance(ema9, pd.Series):
                ema9 = ema9.iloc[0]
                
            is_protected = False
            if side == 'long' and ema3 > ema9:
                is_protected = True
            elif side == 'short' and ema3 < ema9:
                is_protected = True
                
            if is_protected:
                saved_count += 1
                print(f"[{symbol} {side.upper()}] Closed at {closed_at_str} - WOULD BE SAVED! (EMA3: {ema3:.4f}, EMA9: {ema9:.4f})")
            else:
                print(f"[{symbol} {side.upper()}] Closed at {closed_at_str} - STILL CLOSED. (EMA3: {ema3:.4f}, EMA9: {ema9:.4f})")
                
        except Exception as e:
            print(f"Error checking {symbol}: {e}")
            
    print(f"\nResumen: {saved_count} de {total} posiciones habrían evitado el cierre con este nuevo cambio.")

if __name__ == '__main__':
    main()
