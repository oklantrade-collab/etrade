import os
import sys
import asyncio

# Load .env manually for standalone test
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    with open(dotenv_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

from app.execution.providers.ctrader_provider import CTraderProtobufProvider

async def test_ctrader():
    print(f"FOREX_MODE: {os.getenv('FOREX_MODE')}")
    print(f"CTRADER_ENV: {os.getenv('CTRADER_ENV')}")
    
    provider = CTraderProtobufProvider(
        client_id=os.getenv('CTRADER_CLIENT_ID'),
        client_secret=os.getenv('CTRADER_CLIENT_SECRET'),
        account_id=int(os.getenv('CTRADER_ACCOUNT_ID', 0)),
        access_token=os.getenv('CTRADER_ACCESS_TOKEN'),
        environment=os.getenv('CTRADER_ENV', 'demo')
    )
    
    print("Conectando a cTrader...")
    connected = await provider.connect()
    if not connected:
        print("❌ Fallo la conexion a cTrader.")
        return
    print("✅ Conexion exitosa.")
    
    print("Obteniendo informacion de la cuenta...")
    info = await provider.get_account_balance()
    if info:
        print("✅ Informacion obtenida:")
        print(f"   - Balance: {info.get('balance', 0)} USD")
        print(f"   - Leverage: 1:{info.get('leverage', 0)}")
        print(f"   - Equity: {info.get('equity', 0)} USD")
    else:
        print("❌ No se pudo obtener la informacion de la cuenta.")
        
    await provider.disconnect()

if __name__ == '__main__':
    asyncio.run(test_ctrader())
