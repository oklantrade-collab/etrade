import asyncio
from app.core.supabase_client import get_supabase

async def query():
    sb = get_supabase()
    res = sb.table("stocks_positions").select("*").eq("ticker", "INFQ").order("id", desc=True).limit(5).execute()
    for row in res.data:
        print(row)

if __name__ == "__main__":
    asyncio.run(query())
