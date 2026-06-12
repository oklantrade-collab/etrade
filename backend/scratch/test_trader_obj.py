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
    
    connected = await provider.connect()
    
    if connected:
        from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOATraderReq
        request = ProtoOATraderReq()
        request.ctidTraderAccountId = int(provider.account_id)
        
        provider._last_trader = None
        await provider._send_request(request)
        for _ in range(50):
            if provider._last_trader:
                break
            await asyncio.sleep(0.1)
        
        trader = provider._last_trader
        print(dir(trader))
        print("Balance:", getattr(trader, 'balance', None))
        print("Equity:", getattr(trader, 'equity', None))
        print("FreeMargin:", getattr(trader, 'marginFree', getattr(trader, 'freeMargin', None)))

if __name__ == "__main__":
    asyncio.run(main())
