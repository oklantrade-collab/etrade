from app.core.supabase_client import get_supabase
import asyncio

async def fetch_recent_swing_logs():
    sb = get_supabase()
    res = sb.table('system_logs').select('*').eq('module', 'SWING').order('created_at', desc=True).limit(20).execute()
    for l in res.data:
        print(f"[{l['created_at']}] {l['message']}")

if __name__ == "__main__":
    asyncio.run(fetch_recent_swing_logs())
