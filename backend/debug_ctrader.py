import asyncio
import os
from dotenv import load_dotenv
from app.execution.providers.ctrader_provider import CTraderProtobufProvider

async def debug():
    load_dotenv()
    client_id = os.getenv('CTRADER_CLIENT_ID')
    client_secret = os.getenv('CTRADER_CLIENT_SECRET')
    account_id = os.getenv('CTRADER_ACCOUNT_ID')
    access_token = os.getenv('CTRADER_ACCESS_TOKEN')
    
    p = CTraderProtobufProvider(client_id, client_secret, account_id, access_token, 'demo')
    await p.connect()
    # Wait for symbols to load
    await asyncio.sleep(5)
    
    print("SYMBOL IDS:", p._symbol_ids)
    
    await p.disconnect()

if __name__ == "__main__":
    asyncio.run(debug())
