import asyncio
from app.core.supabase_client import get_supabase

async def cleanup():
    sb = get_supabase()
    res = sb.table("technical_scores").delete().eq("ticker", "TESTDUMMY").execute()
    print(f"Deleted TESTDUMMY: {res.data}")
    
    # Delete any record with null timestamp if it's causing issues
    res2 = sb.table("technical_scores").delete().is_("timestamp", "null").execute()
    print(f"Deleted null timestamps: {res2.data}")

if __name__ == "__main__":
    asyncio.run(cleanup())
