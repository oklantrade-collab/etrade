
from app.core.supabase_client import get_supabase
import asyncio

async def test_count():
    sb = get_supabase()
    res = sb.table("positions").select("id", count="exact").eq("status", "open").limit(0).execute()
    print(f"Count with limit(0): {res.count}")
    
    res2 = sb.table("positions").select("id", count="exact").eq("status", "open").limit(1).execute()
    print(f"Count with limit(1): {res2.count}")
    
    res3 = sb.table("positions").select("id").eq("status", "open").execute()
    print(f"Count by len(data): {len(res3.data)}")

if __name__ == "__main__":
    asyncio.run(test_count())
