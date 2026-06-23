import os
import sys
sys.path.append('c:\\Fuentes\\eTrade\\backend')
import pandas as pd
import asyncio
from app.execution.providers.ctrader_provider import CTraderProtobufProvider
from ta.volatility import BollingerBands

async def main():
    p = CTraderProtobufProvider()
    await p.connect()
    df = await p.get_ohlcv('EURUSD', '15m', '2d')
    indicator_bb = BollingerBands(close=df["close"], window=20, window_dev=2)
    df['bb_lower'] = indicator_bb.bollinger_lband()
    last = df.tail(10)
    print(last[['timestamp', 'close', 'bb_lower']].to_string())
    await p.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
