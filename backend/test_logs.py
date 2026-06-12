import asyncio
from app.core.supabase_client import get_supabase

async def main():
    sb = get_supabase()
    res = sb.table("system_logs").select("*").ilike("message", "%SingleAPIResponse%").order("created_at", desc=True).limit(10).execute()
    for row in res.data:
        print(f"[{row['created_at']}] {row['level']} - {row['message']}")
    
    res = sb.table("system_logs").select("*").ilike("message", "%TypeError%").order("created_at", desc=True).limit(10).execute()
    for row in res.data:
        print(f"[{row['created_at']}] {row['level']} - {row['message']}")

if __name__ == "__main__":
    asyncio.run(main())
