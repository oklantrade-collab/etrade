import asyncio
import os
import dotenv

root_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

async def main():
    from app.execution.data_provider import BinanceCryptoProvider
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    provider = BinanceCryptoProvider(api_key=api_key, api_secret=api_secret, market="futures", testnet=False)
    client = await provider._get_async_client()
    pos = await client.futures_position_information()
    active = [p for p in pos if float(p.get("positionAmt", 0)) != 0]
    print(f"ACTIVE BINANCE POSITIONS: {len(active)}")
    for a in active:
        print(a.get("symbol"), a.get("positionAmt"), a.get("entryPrice"), a.get("markPrice"), a.get("unRealizedProfit"))
    await client.close_connection()

if __name__ == '__main__':
    asyncio.run(main())
