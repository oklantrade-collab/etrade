from app.core.supabase_client import get_supabase
import asyncio

async def check_recent_paper_trades():
    sb = get_supabase()
    res = sb.table('paper_trades').select('symbol, rule_code, closed_at, total_pnl_usd').order('closed_at', desc=True).limit(10).execute()
    for t in res.data:
        print(f"Time: {t['closed_at']}, Symbol: {t['symbol']}, Rule: {t['rule_code']}, PnL: {t['total_pnl_usd']}")

if __name__ == "__main__":
    asyncio.run(check_recent_paper_trades())
