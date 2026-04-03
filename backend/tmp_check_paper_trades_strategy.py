from app.core.supabase_client import get_supabase
import asyncio

async def check_paper_trades_strategy():
    sb = get_supabase()
    res = sb.table('paper_trades').select('id, symbol, rule_code, closed_at')\
        .eq('symbol', 'ADAUSDT')\
        .order('closed_at', desc=True)\
        .limit(10).execute()
    
    for t in res.data:
        print(f"ID: {t['id']}, RuleCode: {t['rule_code']}, Closed: {t['closed_at']}")

if __name__ == "__main__":
    asyncio.run(check_paper_trades_strategy())
