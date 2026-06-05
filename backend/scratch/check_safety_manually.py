import asyncio
from app.core.supabase_client import get_supabase
from app.core.safety_manager import check_subprocesses_safety

async def main():
    sb = get_supabase()
    print("Running check_subprocesses_safety()...")
    res = await check_subprocesses_safety(sb)
    print("Forex failed:", res['forex']['failed'])
    print("Forex checks:", res['forex']['checks'])
    print("Crypto failed:", res['crypto']['failed'])
    print("Crypto checks:", res['crypto']['checks'])

if __name__ == '__main__':
    asyncio.run(main())
