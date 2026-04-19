import os
import sys
import asyncio
import time
from datetime import datetime

# Resolver rutas
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from dotenv import load_dotenv
load_dotenv()

from app.execution.providers.ctrader_provider import CTraderProtobufProvider
from app.core.logger import log_info

async def send_manual_buy():
    # Cargar credenciales
    client_id = os.getenv('CTRADER_CLIENT_ID')
    client_secret = os.getenv('CTRADER_CLIENT_SECRET')
    account_id = int(os.getenv('CTRADER_ACCOUNT_ID', 0))
    access_token = os.getenv('CTRADER_ACCESS_TOKEN')
    env = os.getenv('CTRADER_ENV', 'demo')

    log_info('MANUAL', f"Iniciando orden manual BUY MARKET USDJPY ({env})...")

    provider = CTraderProtobufProvider(
        client_id=client_id,
        client_secret=client_secret,
        account_id=account_id,
        access_token=access_token,
        environment=env
    )

    connected = await provider.connect()
    if not connected:
        print("Fallo de conexión")
        return

    # Esperar a que se carguen los IDs de símbolos
    await asyncio.sleep(2)
    
    # 0.01 lotes es el mínimo estándar
    res = await provider.place_order(
        symbol='USDJPY',
        side='buy',
        order_type='market',
        quantity=0.01
    )

    print("Respuesta de orden:", res)
    
    if res.get('status') == 'submitted':
        # Guardar en Supabase para que aparezca en el Dashboard
        try:
            from app.core.supabase_client import get_supabase
            sb = get_supabase()
            price = await provider.get_current_price('USDJPY')
            pos = {
                'symbol': 'USDJPY',
                'side': 'long',
                'lots': 0.01,
                'entry_price': price or 150.0, # Fallback si no hay precio instantáneo
                'status': 'active',
                'mode': env,
                'rule_code': 'MANUAL',
                'opened_at': datetime.utcnow().isoformat()
            }
            db_res = sb.table('forex_positions').insert(pos).execute()
            print("OK - Sincronizado con Supabase:", db_res.data)
        except Exception as e:
            print(f"ERROR al guardar en DB: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # Dar tiempo a que cTrader procese y se vean logs
    await asyncio.sleep(5)
    
    await provider.disconnect()

if __name__ == '__main__':
    asyncio.run(send_manual_buy())
