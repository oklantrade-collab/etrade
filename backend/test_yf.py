import os
import sys
import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.workers.stocks_scheduler import get_stocks_config

print("Today:", datetime.date.today())
print("Day:", datetime.datetime.now().strftime('%A'))

print("\n--- CONFIG ---")
print(get_stocks_config())

try:
    import yfinance as yf
    df = yf.download('AAPL', period='1d', interval='5m')
    print("\n--- AAPL YFINANCE ---")
    print(df)
except Exception as e:
    print(e)
