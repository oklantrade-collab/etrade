from app.core.supabase_client import get_supabase
import asyncio

async def check_positions():
    sb = get_supabase()
    res = sb.table('positions').select('symbol, side, status').limit(5).execute()
    for p in res.data:
        print(f"Symbol: {p['symbol']}, Side: {p['side']}, Status: {p['status']}")

if __name__ == "__main__":
    asyncio.run(check_positions())
