import sys
import os
import asyncio

root_dir = 'c:/Fuentes/eTrade'
sys.path.insert(0, root_dir)
sys.path.insert(0, 'c:/Fuentes/eTrade/backend')

# Load .env
dotenv_path = os.path.join(root_dir, 'backend', '.env')
with open(dotenv_path, 'rb') as f:
    raw = f.read()
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        content = raw.decode('utf-16')
    else:
        content = raw.decode('utf-8', errors='ignore')
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k, v = k.strip(), v.strip()
        if v and v[0] in ('"', "'") and v[-1] == v[0]:
            v = v[1:-1]
        os.environ[k] = v

from app.execution.providers.ctrader_provider import CTraderProtobufProvider
from supabase import create_client

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

async def main():
    print("[1] Conectando a cTrader/IC Markets OpenAPI...")
    provider = CTraderProtobufProvider(
        client_id=os.getenv('CTRADER_CLIENT_ID'),
        client_secret=os.getenv('CTRADER_CLIENT_SECRET'),
        account_id=int(os.getenv('CTRADER_ACCOUNT_ID', 0)),
        access_token=os.getenv('CTRADER_ACCESS_TOKEN'),
        environment=os.getenv('CTRADER_ENV', 'live'),
    )
    connected = await provider.connect()
    if not connected:
        print("[ERROR] No se pudo conectar a cTrader. Verifica credenciales o estado de red.")
        return

    print("[2] Consultando posiciones abiertas en la cuenta de IC Markets...")
    positions = await provider.get_open_positions()
    print(f"    Posiciones encontradas en IC Markets: {len(positions)}")

    for p in positions:
        print("    -> Position RAW:", p)

    await provider.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
