"""
Test completo de conexión cTrader Protobuf.
Ejecutar con: python test_ctrader_protobuf.py
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.execution.providers.ctrader_provider \
    import CTraderProtobufProvider

async def test_all():
    # Force SelectorEventLoop on Windows for Twisted compatibility
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    print("=" * 50)
    print("TEST CTRADER PROTOBUF TCP")
    print("=" * 50 + "\n")

    provider = CTraderProtobufProvider(
        client_id    = os.getenv('CTRADER_CLIENT_ID'),
        client_secret= os.getenv('CTRADER_CLIENT_SECRET'),
        account_id   = int(os.getenv(
            'CTRADER_ACCOUNT_ID', 0
        )),
        access_token = os.getenv('CTRADER_ACCESS_TOKEN'),
        environment  = os.getenv('CTRADER_ENV','demo'),
    )

    # TEST 1: Conexión TCP
    print("TEST 1: Conectando via Protobuf TCP...")
    connected = await provider.connect()
    assert connected, "FAIL: No se pudo conectar"
    print("[OK] Conexion establecida\n")

    # TEST 2: Balance
    print("TEST 2: Obteniendo balance...")
    balance = await provider.get_account_balance()
    assert balance, "FAIL: No se obtuvo balance"
    print(f"[OK] Balance: "
          f"${balance['balance']:,.2f} "
          f"{balance.get('currency','USD')}")
    print(f"   Equity: ${balance['equity']:,.2f}")
    print(f"   Libre:  ${balance['margin_free']:,.2f}\n")

    # TEST 3: Subscripción a precios en tiempo real
    print("TEST 3: Subscribiendo a EURUSD y GBPUSD...")
    prices_received = []

    def price_callback(symbol, mid, bid, ask):
        prices_received.append({
            'symbol': symbol,
            'mid':    mid,
            'bid':    bid,
            'ask':    ask,
        })
        print(f"  [TICK] {symbol}: "
              f"mid={mid:.5f} "
              f"bid={bid:.5f} "
              f"ask={ask:.5f}")

    await provider.subscribe_prices(
        symbols  = ['EURUSD', 'GBPUSD',
                    'USDJPY', 'XAUUSD'],
        callback = price_callback
    )

    print("Esperando precios (5 segundos)...")
    await asyncio.sleep(5)

    assert len(prices_received) > 0, \
        "FAIL: No se recibieron precios"
    print(f"[OK] {len(prices_received)} "
          f"ticks recibidos\n")

    # TEST 4: Precio actual
    print("TEST 4: Precio actual EURUSD...")
    eurusd = await provider.get_current_price(
        'EURUSD'
    )
    assert eurusd > 0, "FAIL: Precio = 0"
    print(f"[OK] EURUSD mid: {eurusd:.5f}\n")

    # TEST 5: Velas históricas
    print("TEST 5: Descargando velas EURUSD 15m...")
    df = await provider.get_ohlcv(
        'EURUSD', '15m', limit=100
    )
    assert len(df) > 0, "FAIL: Sin velas"
    print(f"[OK] {len(df)} velas descargadas")
    print(f"   Ultima vela: {df.index[-1]}")
    print(f"   Close:       {df['close'].iloc[-1]:.5f}")
    print(f"   High:        {df['high'].iloc[-1]:.5f}")
    print(f"   Low:         {df['low'].iloc[-1]:.5f}\n")

    # TEST 6: Múltiples timeframes
    print("TEST 6: Multiples timeframes...")
    for tf in ['5m', '1h', '4h']:
        df_tf = await provider.get_ohlcv(
            'EURUSD', tf, limit=50
        )
        print(f"  EURUSD/{tf}: {len(df_tf)} velas "
              f"| last close: "
              f"{df_tf['close'].iloc[-1]:.5f}")

    print("\n" + "=" * 50)
    print("TODOS LOS TESTS PASARON [OK]")
    print("cTrader Protobuf TCP funcionando")
    print("=" * 50)

    await provider.disconnect()

asyncio.run(test_all())
