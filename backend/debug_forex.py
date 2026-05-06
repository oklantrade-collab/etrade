import asyncio
from app.core.supabase_client import get_supabase

async def debug():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('status', 'open').execute()
    print("OPEN POSITIONS:")
    for p in res.data:
        print(f"ID: {p['id']}, Symbol: {p['symbol']}, Entry: {p['entry_price']}, Current: {p.get('current_price')}")
    
    res = sb.table('forex_positions').select('*').order('created_at', desc=True).limit(20).execute()
    print("\nLAST 20 POSITIONS:")
    for p in res.data:
        print(f"ID: {p['id']}, Symbol: {p['symbol']}, Status: {p['status']}, Entry: {p['entry_price']}, Reason: {p.get('close_reason')}")

if __name__ == "__main__":
    asyncio.run(debug())
