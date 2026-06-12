import asyncio
from binance import AsyncClient, BinanceSocketManager

async def test_empty_streams():
    try:
        client = await AsyncClient.create("", "")
        bsm = BinanceSocketManager(client)
        streams = []
        async with bsm.multiplex_socket(streams) as ms:
            res = await ms.recv()
            print(res)
    except Exception as e:
        print(f"Exception Type: {type(e)}")
        print(f"Exception str: '{str(e)}'")
        
asyncio.run(test_empty_streams())
