import yfinance as yf
import pandas as pd

symbols = ['KXIN', 'HPAI', 'DOMH', 'MUD', 'NIO']
for s in symbols:
    try:
        ticker = yf.Ticker(s)
        df = ticker.history(period='1d')
        if not df.empty:
            vol = df['Volume'].iloc[-1]
            price = df['Close'].iloc[-1]
            print(f"{s}: Price=${price:.2f}, Volume={vol:,.0f}")
        else:
            print(f"{s}: No data")
    except Exception as e:
        print(f"{s}: Error {e}")
