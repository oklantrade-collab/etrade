from app.core.supabase_client import get_supabase
import asyncio

async def check_recent_pending():
    sb = get_supabase()
    res = sb.table('pending_orders').select('id, symbol, timeframe, created_at').eq('status', 'pending').order('created_at', desc=True).limit(5).execute()
    for o in res.data:
        print(f"ID: {o['id']}, Symbol: {o['symbol']}, TF: {o['timeframe']}, Created: {o['created_at']}")

if __name__ == "__main__":
    asyncio.run(check_recent_pending())
