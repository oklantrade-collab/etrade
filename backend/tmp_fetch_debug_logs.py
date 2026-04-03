from app.core.supabase_client import get_supabase
import asyncio

async def fetch_debug_logs():
    sb = get_supabase()
    res = sb.table('system_logs').select('*').in_('module', ['DEBUG_CLOSE', 'DEBUG_PARTIAL']).order('created_at', desc=True).limit(10).execute()
    for l in res.data:
        print(f"[{l['created_at']}] {l['message']}")

if __name__ == "__main__":
    asyncio.run(fetch_debug_logs())
