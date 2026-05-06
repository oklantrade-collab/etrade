import asyncio
import os
from dotenv import load_dotenv
from app.execution.providers.ctrader_provider import CTraderProtobufProvider
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *
from ctrader_open_api import Protobuf

async def debug():
    load_dotenv()
    client_id = os.getenv('CTRADER_CLIENT_ID')
    client_secret = os.getenv('CTRADER_CLIENT_SECRET')
    account_id = os.getenv('CTRADER_ACCOUNT_ID')
    access_token = os.getenv('CTRADER_ACCESS_TOKEN')
    
    p = CTraderProtobufProvider(client_id, client_secret, account_id, access_token, 'demo')
    
    def on_msg(client, msg):
        if msg.payloadType == 2117: # ProtoOASymbolByIdRes
            res = ProtoOASymbolByIdRes()
            res.ParseFromString(msg.payload)
            for s in res.symbol:
                print(f"SYMBOL: {s.symbolName}, Digits: {s.digits}, Pip Position: {s.pipPosition}")

    await p.connect()
    p._client.setMessengerCallback(on_msg)
    await asyncio.sleep(2)
    
    # Find XAUUSD ID (already loaded in connect)
    xau_id = None
    for sid, name in p._symbol_ids.items():
        if name == 'XAUUSD':
            xau_id = sid
            break
    
    if xau_id:
        print(f"XAUUSD ID: {xau_id}")
        req = ProtoOASymbolByIdReq()
        req.ctidTraderAccountId = int(account_id)
        req.symbolId.append(xau_id)
        p._client.send(req)
        await asyncio.sleep(5)
    else:
        print("XAUUSD not found")
    
    await p.disconnect()

if __name__ == "__main__":
    asyncio.run(debug())
