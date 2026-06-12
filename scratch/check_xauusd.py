import asyncio
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').order('closed_at', desc=True).limit(5).execute()
    for row in res.data:
        print(f"ID: {row.get('id')} - {row.get('status')} {row.get('side')} - Entry: {row.get('entry_price')} - Close: {row.get('current_price')} - PNL: {row.get('pnl_usd')} - Partial: {row.get('partial_pnl_usd')} - Lots: {row.get('lots')} - Size: {row.get('size')} - Reason: {row.get('close_reason')}")

if __name__ == "__main__":
    asyncio.run(check())
