import asyncio
from app.core.supabase_client import get_supabase

async def debug():
    sb = get_supabase()
    res = sb.table('market_snapshot').select('*').eq('symbol', 'XAUUSD').execute()
    print("XAUUSD SNAPSHOT:")
    if res.data:
        s = res.data[0]
        print(f"Price: {s.get('price')}, Basis: {s.get('basis')}, U6: {s.get('upper_6')}, L6: {s.get('lower_6')}")

if __name__ == "__main__":
    asyncio.run(debug())
