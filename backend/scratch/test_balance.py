import asyncio
import os
from dotenv import load_dotenv

async def main():
    load_dotenv()
    from app.execution.providers.ctrader_provider import CTraderProtobufProvider
    
    provider = CTraderProtobufProvider(
        client_id=os.getenv('CTRADER_CLIENT_ID'),
        client_secret=os.getenv('CTRADER_CLIENT_SECRET'),
        account_id=os.getenv('CTRADER_ACCOUNT_ID'),
        access_token=os.getenv('CTRADER_ACCESS_TOKEN'),
        environment=os.getenv('CTRADER_ENV', 'demo')
    )
    
    print("Connecting...")
    connected = await provider.connect()
    print("Connected:", connected)
    
    if connected:
        print("Getting balance...")
        balance = await provider.get_account_balance()
        print("Balance:", balance)

if __name__ == "__main__":
    asyncio.run(main())
