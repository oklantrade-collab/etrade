from app.core.supabase_client import get_supabase
import asyncio

async def check_opening_time():
    sb = get_supabase()
    res = sb.table('positions').select('id, symbol, opened_at, rule_code, status').eq('status', 'closed').eq('symbol', 'ADAUSDT').order('closed_at', desc=True).limit(5).execute()
    for p in res.data:
        print(f"ID: {p['id']}, Opened: {p['opened_at']}, Rule: {p.get('rule_code')}")

if __name__ == "__main__":
    asyncio.run(check_opening_time())
