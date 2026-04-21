import os, sys, asyncio, json
import httpx

async def call_api():
    async with httpx.AsyncClient() as client:
        # Assuming the backend is running on localhost:8000 or similar
        # But wait, I can just call the function directly if I import it.
        pass

# Direct function call is better
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_via_direct_query():
    sb = get_supabase()
    status = 'open'
    res = sb.table('forex_positions')\
        .select('*')\
        .eq('status', status)\
        .order('opened_at', desc=True)\
        .execute()
    print(f"API-like query result count: {len(res.data)}")
    for p in res.data:
        print(f"ID: {p['id']}, Symbol: {p['symbol']}, Status: {p['status']}")

if __name__ == "__main__":
    asyncio.run(check_via_direct_query())
