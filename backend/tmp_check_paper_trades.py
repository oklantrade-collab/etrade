from app.core.supabase_client import get_supabase
import asyncio

async def check_paper_trades():
    sb = get_supabase()
    res = sb.table('paper_trades').select('symbol, side, entry_price, exit_price, total_pnl_usd').eq('symbol', 'ADAUSDT').order('closed_at', desc=True).limit(5).execute()
    for t in res.data:
        print(f"Symbol: {t['symbol']}, Side: {t['side']}, Entry: {t['entry_price']}, Exit: {t['exit_price']}, PnL: {t['total_pnl_usd']}")

if __name__ == "__main__":
    asyncio.run(check_paper_trades())
