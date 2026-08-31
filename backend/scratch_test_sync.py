import asyncio
import os
import dotenv

root_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

async def main():
    from app.execution.broker_sync import GLOBAL_BROKER_SYNC
    res = await GLOBAL_BROKER_SYNC.sync_binance_futures()
    print("SYNC RESULT:", res)

if __name__ == '__main__':
    asyncio.run(main())
