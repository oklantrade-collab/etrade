import asyncio
from app.core.supabase_client import get_supabase

async def fix():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').eq('status', 'closed').order('closed_at', desc=True).limit(1).execute()
    if res.data:
        row = res.data[0]
        # PNL = (entry - current) * lots for short
        entry = row['entry_price']
        close = row['current_price']
        lots = row['lots']
        correct_pnl = round((entry - close) * lots, 4)
        print(f'Fixing ID {row["id"]} from {row["pnl_usd"]} to {correct_pnl}')
        sb.table('forex_positions').update({'pnl_usd': correct_pnl}).eq('id', row['id']).execute()

if __name__ == "__main__":
    asyncio.run(fix())
