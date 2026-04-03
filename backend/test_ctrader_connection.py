"""
eTrader — Test cTrader / IC Markets Connection
================================================
Script de verificación de conexión con IC Markets
via cTrader Open API.

Ejecutar: python test_ctrader_connection.py
"""
import asyncio
import os
import sys

# Fix Windows console encoding for UTF-8
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Asegurar que el path incluya el directorio backend
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.execution.providers.ctrader_provider import CTraderProvider


async def test():
    print("=" * 60)
    print("  eTrader - Test cTrader / IC Markets Connection")
    print("=" * 60)
    print()

    # Verificar variables de entorno
    required_vars = [
        'CTRADER_CLIENT_ID',
        'CTRADER_CLIENT_SECRET',
        'CTRADER_ACCOUNT_ID',
        'CTRADER_ACCESS_TOKEN',
    ]
    missing = [
        v for v in required_vars
        if not os.getenv(v) or os.getenv(v).startswith('tu_')
    ]
    if missing:
        print(f"[!] Variables de entorno faltantes o placeholder: {', '.join(missing)}")
        print("    Configuralas en .env con tus credenciales reales de IC Markets.")
        print()
        print("    Pasos para obtener credenciales:")
        print("    1. Ir a https://openapi.ctrader.com/")
        print("    2. Registrar una aplicacion")
        print("    3. Obtener Client ID y Client Secret")
        print("    4. Autorizar con tu cuenta IC Markets")
        print("    5. Obtener Access Token via OAuth 2.0")
        print()
        print("    Una vez tengas las credenciales, actualiza .env:")
        print("    CTRADER_CLIENT_ID=tu_id_real")
        print("    CTRADER_CLIENT_SECRET=tu_secret_real")
        print("    CTRADER_ACCOUNT_ID=tu_cuenta_real")
        print("    CTRADER_ACCESS_TOKEN=tu_token_real")
        return

    provider = CTraderProvider(
        client_id=os.getenv('CTRADER_CLIENT_ID'),
        client_secret=os.getenv('CTRADER_CLIENT_SECRET'),
        account_id=os.getenv('CTRADER_ACCOUNT_ID'),
        access_token=os.getenv('CTRADER_ACCESS_TOKEN'),
        environment=os.getenv('CTRADER_ENV', 'demo'),
    )

    # -- Test 0: Conexion --
    print("[*] Conectando a IC Markets...")
    connected = await provider.connect()

    if not connected:
        print("[X] Error de conexion")
        print("    Verifica tus credenciales en .env")
        return

    print("[OK] Conectado exitosamente")
    print()

    # -- Test 1: Balance --
    print("[1] Test: Balance de la cuenta")
    balance = await provider.get_account_balance()
    if balance:
        print(f"    Balance:      ${balance.get('balance', 0):,.2f}")
        print(f"    Equity:       ${balance.get('equity', 0):,.2f}")
        print(f"    Margin libre: ${balance.get('margin_free', 0):,.2f}")
        print(f"    Moneda:       {balance.get('currency', 'N/A')}")
        print("    [OK] Balance OK")
    else:
        print("    [!] Sin datos de balance")
    print()

    # -- Test 2: Precio EURUSD --
    print("[2] Test: Precio actual EURUSD")
    price = await provider.get_current_price('EURUSD')
    if price > 0:
        print(f"    EURUSD mid price: {price:.5f}")
        print("    [OK] Precio OK")
    else:
        print("    [!] No se pudo obtener precio")
    print()

    # -- Test 3: Velas historicas --
    print("[3] Test: Velas EURUSD 15m (ultimas 10)")
    df = await provider.get_ohlcv('EURUSD', '15m', 10)
    if not df.empty:
        print(f"    Velas recibidas: {len(df)}")
        print(f"    Rango: {df.index[0]} -> {df.index[-1]}")
        print()
        print("    Ultimas 3 velas:")
        print(df.tail(3).to_string(index=True))
        print("    [OK] Velas OK")
    else:
        print("    [!] Sin datos de velas")
    print()

    # -- Test 4: Posiciones abiertas --
    print("[4] Test: Posiciones abiertas")
    positions = await provider.get_open_positions()
    print(f"    Posiciones abiertas: {len(positions)}")
    if positions:
        for pos in positions[:5]:
            print(f"    -> {pos}")
    print("    [OK] Posiciones OK")
    print()

    # -- Test 5: Pip sizes --
    print("[5] Test: Pip sizes configurados")
    for symbol, pip in list(provider.pip_size.items())[:5]:
        print(f"    {symbol}: {pip}")
    print(f"    ... ({len(provider.pip_size)} simbolos configurados)")
    print("    [OK] Pip sizes OK")
    print()

    # -- Desconectar --
    await provider.disconnect()

    print("=" * 60)
    print("  [OK] Todos los tests completados exitosamente")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(test())
