import asyncio
import os
import sys
import pandas as pd
import yfinance as yf

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analysis.stocks_indicators import calculate_stock_indicators
from app.analysis.movement_classifier import classify_movement
from app.analysis.fibonacci_bb import fibonacci_bollinger

async def analyze_ticker(ticker):
    print(f"\n--- Analyzing {ticker} ---")
    t_obj = yf.Ticker(ticker)
    df_15m = t_obj.history(interval="15m", period="5d")
    df_4h = t_obj.history(interval="1h", period="15d")
    df_1d = t_obj.history(period="60d")
    
    df_15m.columns = [c.lower() for c in df_15m.columns]
    df_4h.columns = [c.lower() for c in df_4h.columns]
    df_1d.columns = [c.lower() for c in df_1d.columns]

    if df_15m.empty or df_1d.empty:
        print(f"No data for {ticker}")
        return

    # 1. indicators
    ind_15m = calculate_stock_indicators(df_15m, "15m", ticker)
    ind_1d = calculate_stock_indicators(df_1d, "1d", ticker)
    
    # 2. Add Fibonacci Bands
    df_15m = fibonacci_bollinger(df_15m)
    
    current_price = df_15m.iloc[-1]["close"]
    mov_15m = classify_movement(df_15m) # Use default lookback
    
    print(f"Current Price: {current_price:.2f}")
    print(f"Movement 15m: {mov_15m['movement_type']} (Zone: {mov_15m['fib_zone_current']})")
    print(f"RSI 15m: {ind_15m.get('rsi_14', 0):.2f}")
    
    ema_50 = ind_1d.get("ema_50", 0)
    ema_200 = ind_1d.get("ema_200", 0)
    print(f"EMA 50/200 (1d): {ema_50:.2f} / {ema_200:.2f} ({'Golden Cross' if ema_50 > ema_200 else 'Death Cross'})")

async def main():
    tickers = ["IFRX", "POET", "FTEK", "CMPX"]
    for t in tickers:
        try:
            await analyze_ticker(t)
        except Exception as e:
            print(f"Error analyzing {t}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
