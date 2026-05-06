import asyncio
from app.core.supabase_client import get_supabase

async def debug():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('symbol', 'EURUSD').execute()
    print("EURUSD POSITIONS:")
    for p in res.data:
        print(f"ID: {p['id']}, Entry: {p['entry_price']}, Status: {p['status']}")

if __name__ == "__main__":
    asyncio.run(debug())
