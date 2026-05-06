import asyncio
import os
import sys
import pandas as pd

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase
from app.data.yfinance_provider import YFinanceProvider

async def check_gdc_data():
    provider = YFinanceProvider()
    df_15m = await provider.get_ohlcv("GDC", interval="15m", period="5d")
    df_4h = await provider.get_ohlcv("GDC", interval="4h", period="20d")
    
    print("Last 3 15m candles:")
    print(df_15m.tail(3))
    
    print("\nLast 3 4h candles:")
    print(df_4h.tail(3))

if __name__ == "__main__":
    asyncio.run(check_gdc_data())
