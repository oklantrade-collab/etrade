import asyncio
import os
import pandas as pd
from dotenv import load_dotenv
from app.core.supabase_client import get_supabase
from app.execution.data_provider import BinanceCryptoProvider
from app.analysis.indicators_v2 import calculate_emas, calculate_ema_angles, calculate_macd_4c
from app.analysis.fibonacci_bb import fibonacci_bollinger

load_dotenv('c:/Fuentes/eTrade/backend/.env')

async def diagnose():
    provider = BinanceCryptoProvider(
        api_key=os.getenv('BINANCE_API_KEY'),
        api_secret=os.getenv('BINANCE_API_SECRET'),
        market='futures',
        testnet=True
    )
    
    symbol = 'BTCUSDT'
    timeframe = '15m'
    limit = 2500
    
    print(f"Descargando {limit} velas de {symbol}...")
    df = await provider.get_ohlcv(symbol, timeframe, limit=limit)
    
    print("Calculando indicadores...")
    df['hlc3'] = (df['high'] + df['low'] + df['close']) / 3
    df = calculate_emas(df)
    df = fibonacci_bollinger(df)
    df = calculate_ema_angles(df)
    df = calculate_macd_4c(df)
    
    # Simular calculo de basis (VWMA en PineScript, aqui usamos la 'basis' de FibBB)
    # En fibonacci_bb.py se asume que existe 'basis'.
    
    # Cruces (Manual emulation of PineScript 'ta.cross')
    def cross_above(s1, s2):
        return (s1 > s2) & (s1.shift(1) <= s2.shift(1))
    
    def cross_below(s1, s2):
        return (s1 < s2) & (s1.shift(1) >= s2.shift(1))

    ema4 = df['ema4'] # EMA50
    basis = df['basis'] # VWMA
    
    count_aa13 = cross_above(ema4, basis).sum()
    count_aa23 = ((df['ema9_angle'] >= 0) & (df['ema50_angle'] >= 0)).sum()
    count_bb12 = cross_below(ema4, basis).sum()
    
    print("\n" + "="*50)
    print(" DIAGNÓSTICO DE REGLAS (BTCUSDT 2500 VELAS)")
    print("="*50)
    print(f"Aa13 (EMA50 cross basis up):   {count_aa13} veces")
    print(f"Aa23 (EMA9 & EMA50 angle >= 0): {count_aa23} veces")
    print(f"Bb12 (EMA50 cross basis down): {count_bb12} veces")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(diagnose())
