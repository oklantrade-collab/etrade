from app.core.supabase_client import get_supabase
import asyncio

async def check_pending_orders_rules():
    sb = get_supabase()
    res = sb.table('pending_orders').select('*').limit(10).execute()
    for o in res.data:
        print(f"ID: {o['id']}, Symbol: {o['symbol']}, Rule: {o.get('rule_code')}, Status: {o['status']}")

if __name__ == "__main__":
    asyncio.run(check_pending_orders_rules())
