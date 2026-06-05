import asyncio
import os
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.execution.providers.ctrader_provider import CTraderProtobufProvider

async def check_ids():
    provider = CTraderProtobufProvider(
        client_id    = os.getenv('CTRADER_CLIENT_ID'),
        client_secret= os.getenv('CTRADER_CLIENT_SECRET'),
        account_id   = int(os.getenv('CTRADER_ACCOUNT_ID', 0)),
        access_token = os.getenv('CTRADER_ACCESS_TOKEN'),
        environment  = os.getenv('CTRADER_ENV','demo'),
    )
    
    connected = await provider.connect()
    if not connected:
        print("Failed to connect")
        return
        
    print("Connected to cTrader")
    
    # We can get the client and print the symbols mapped in state
    print("Symbol IDs in CTraderProtobufProvider:")
    for name, sid in provider._symbol_ids.items():
        print(f"Name: {name} | ID: {sid}")
        
    await provider.disconnect()

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check_ids())
