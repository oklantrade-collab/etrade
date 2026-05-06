import asyncio
import os
from dotenv import load_dotenv
from app.execution.providers.ctrader_provider import CTraderProtobufProvider
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *

async def debug():
    load_dotenv()
    client_id = os.getenv('CTRADER_CLIENT_ID')
    client_secret = os.getenv('CTRADER_CLIENT_SECRET')
    account_id = os.getenv('CTRADER_ACCOUNT_ID')
    access_token = os.getenv('CTRADER_ACCESS_TOKEN')
    
    p = CTraderProtobufProvider(client_id, client_secret, account_id, access_token, 'demo')
    
    def on_msg(client, msg):
        if msg.payloadType == 2115: # SymbolsListRes
            print("Received Symbols List")
        if msg.payloadType == 2131: # SpotEvent
            res = ProtoOASpotEvent()
            res.ParseFromString(msg.payload)
            print(f"SPOT: SymbolID={res.symbolId}, Bid={res.bid}, Ask={res.ask}")

    await p.connect()
    p._client.setMessengerCallback(on_msg)
    await asyncio.sleep(2)
    
    xau_id = None
    for sid, name in p._symbol_ids.items():
        if name == 'XAUUSD':
            xau_id = sid
            break
    
    if xau_id:
        print(f"XAUUSD ID: {xau_id}. Subscribing...")
        req = ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = int(account_id)
        req.symbolId.append(xau_id)
        p._client.send(req)
        await asyncio.sleep(10)
    else:
        print("XAUUSD not found")
    
    await p.disconnect()

if __name__ == "__main__":
    asyncio.run(debug())
