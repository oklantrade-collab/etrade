import pandas as pd
import yfinance as yf
import numpy as np
import talib
from datetime import datetime, timedelta

symbols = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'EURUSD=X']

def get_data(symbol, interval, days):
    end = datetime.now()
    start = end - timedelta(days=days)
    df = yf.download(symbol, start=start, end=end, interval=interval, progress=False)
    # yfinance sometimes returns MultiIndex columns, flatten them
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    return df

def calculate_indicators(df):
    if len(df) < 200:
        return df
    
    close = df['Close'].values
    high = df['High'].values
    low = df['Low'].values
    
    df['EMA3'] = talib.EMA(close, timeperiod=3)
    df['EMA9'] = talib.EMA(close, timeperiod=9)
    df['EMA20'] = talib.EMA(close, timeperiod=20)
    df['EMA50'] = talib.EMA(close, timeperiod=50)
    df['EMA200'] = talib.EMA(close, timeperiod=200)
    
    df['RSI'] = talib.RSI(close, timeperiod=14)
    
    # Bollinger Bands 20, 2
    upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    df['BB_UPPER'] = upper
    df['BB_LOWER'] = lower
    
    # ATR for stop loss / target estimation
    df['ATR'] = talib.ATR(high, low, close, timeperiod=14)
    
    return df

def simulate():
    total_aa21 = 0
    total_bb21 = 0
    total_aa40 = 0
    total_bb40 = 0
    
    print("Simulando últimas 24 horas (7 días de data para EMAs)...")
    for symbol in symbols:
        try:
            # Need 7 days of 15m data to calculate EMA200 correctly
            df_15m = get_data(symbol, '15m', 7)
            df_15m = calculate_indicators(df_15m)
            
            # Filter to last 24h
            cutoff = datetime.now() - timedelta(days=1)
            # Make cutoff timezone-aware to match yfinance output
            if df_15m.index.tzinfo is not None:
                cutoff = cutoff.replace(tzinfo=df_15m.index.tzinfo)
            df_24h = df_15m[df_15m.index >= cutoff].copy()
            
            aa21_count = 0
            bb21_count = 0
            aa40_count = 0
            bb40_count = 0
            
            for i in range(len(df_24h)):
                row = df_24h.iloc[i]
                
                # Check Aa21 (Trend Pullback LONG)
                # Trend: EMA3 > EMA9 > EMA20 > EMA50 > EMA200
                if row['EMA3'] > row['EMA9'] and row['EMA9'] > row['EMA20'] and row['EMA20'] > row['EMA50'] and row['EMA50'] > row['EMA200']:
                    # Price pullback near EMA20
                    if row['Low'] <= row['EMA20'] * 1.002 and row['High'] >= row['EMA20'] * 0.998:
                        aa21_count += 1
                        
                # Check Bb21 (Trend Pullback SHORT)
                if row['EMA3'] < row['EMA9'] and row['EMA9'] < row['EMA20'] and row['EMA20'] < row['EMA50']:
                    if row['High'] >= row['EMA20'] * 0.998 and row['Low'] <= row['EMA20'] * 1.002:
                        bb21_count += 1
                        
                # Check Aa40 (Capitulation Flash Crash LONG)
                # RSI < 15 and Price < BB_LOWER * 0.98
                if row['RSI'] <= 15 and row['Low'] < row['BB_LOWER'] * 0.98:
                    aa40_count += 1
                    
                # Check Bb40 (Euphoria Flash Crash SHORT)
                if row['RSI'] >= 85 and row['High'] > row['BB_UPPER'] * 1.02:
                    bb40_count += 1
                    
            print(f"[{symbol}] Aa21 (Trend Long): {aa21_count} | Bb21 (Trend Short): {bb21_count} | Aa40 (Crash Long): {aa40_count} | Bb40 (Crash Short): {bb40_count}")
            
            total_aa21 += aa21_count
            total_bb21 += bb21_count
            total_aa40 += aa40_count
            total_bb40 += bb40_count
            
        except Exception as e:
            print(f"Error {symbol}: {e}")

    print("-" * 50)
    print("TOTALES 24 HORAS:")
    print(f"Aa21 (Trend Pullback Long): {total_aa21} órdenes")
    print(f"Bb21 (Trend Pullback Short): {total_bb21} órdenes")
    print(f"Aa40 (Flash Crash Long): {total_aa40} órdenes")
    print(f"Bb40 (Flash Crash Short): {total_bb40} órdenes")
    
if __name__ == "__main__":
    simulate()
