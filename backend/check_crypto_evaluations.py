import asyncio
from app.core.supabase_client import get_supabase

async def main():
    sb = get_supabase()
    res = sb.table("pilot_diagnostics").select("*").eq("symbol", "ETHUSDT").order("timestamp", desc=True).limit(10).execute()
    for row in res.data:
        print(f"[{row['timestamp']}] {row['cycle_type']} - Blocked By: {row['entry_blocked_by']} | Error: {row['error_message']}")

if __name__ == "__main__":
    asyncio.run(main())
