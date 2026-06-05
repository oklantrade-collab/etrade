import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.execution.providers.ctrader_provider import CTraderProtobufProvider
from ctrader_open_api import Protobuf

async def main():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    provider = CTraderProtobufProvider(
        client_id    = os.getenv('CTRADER_CLIENT_ID'),
        client_secret= os.getenv('CTRADER_CLIENT_SECRET'),
        account_id   = int(os.getenv('CTRADER_ACCOUNT_ID', 0)),
        access_token = os.getenv('CTRADER_ACCESS_TOKEN'),
        environment  = os.getenv('CTRADER_ENV','demo'),
    )

    # Let's override the _on_message of the provider to print errors
    old_on_message = provider._on_message
    def new_on_message(client, message):
        msg_type = message.payloadType
        if msg_type == 50 or msg_type == 2142:
            error = Protobuf.extract(message)
            print(f"\n[SERVER ERROR RES] Code: {getattr(error, 'errorCode', 'N/A')} | Desc: {getattr(error, 'description', 'N/A')}")
        old_on_message(client, message)
        
    provider._on_message = new_on_message

    print("Connecting to cTrader...")
    connected = await provider.connect()
    if not connected:
        print("Failed to connect!")
        return

    print("\n--- SYMBOL ID MAPPING ---")
    for name, sid in sorted(provider._symbol_ids.items()):
        if any(sym in name for sym in ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']):
            print(f"Name: {name} -> ID: {sid}")
            
    await provider.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
