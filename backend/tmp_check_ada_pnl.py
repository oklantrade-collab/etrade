from app.core.supabase_client import get_supabase
import asyncio

async def check_ada_positions():
    sb = get_supabase()
    res = sb.table('positions').select('id, symbol, side, entry_price, current_price, realized_pnl, status, closed_at').eq('symbol', 'ADAUSDT').eq('status', 'closed').order('closed_at', desc=True).limit(5).execute()
    for p in res.data:
        print(f"ID: {p['id']}, Symbol: {p['symbol']}, Entry: {p['entry_price']}, Current: {p['current_price']}, PnL: {p['realized_pnl']}, ClosedAt: {p['closed_at']}")

if __name__ == "__main__":
    asyncio.run(check_ada_positions())
