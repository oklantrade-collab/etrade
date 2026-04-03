from app.core.supabase_client import get_supabase
import asyncio

async def check_paper_trade_detail():
    sb = get_supabase()
    # Buscar la que cerro a las 21:50 UTC
    res = sb.table('paper_trades').select('*').eq('symbol', 'ADAUSDT').gte('closed_at', '2026-03-29T21:50:00').lte('closed_at', '2026-03-29T21:50:20').execute()
    for t in res.data:
        print(f"PaperTrade keys: {t.keys()}")
        print(f"Rule: {t.get('rule_code')}")
        print(f"Time: {t['closed_at']}")

if __name__ == "__main__":
    asyncio.run(check_paper_trade_detail())
