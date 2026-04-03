from app.core.supabase_client import get_supabase
import asyncio

async def debug_one_trade():
    sb = get_supabase()
    # Una de las que sale en blanco (-) en el dashboard
    res = sb.table('paper_trades').select('*').eq('symbol', 'ADAUSDT').is_('rule_code', 'null').limit(5).execute()
    for t in res.data:
        print(f"PaperTrade ID: {t['id']}, Rule: {t.get('rule_code')}, Time: {t['closed_at']}")

if __name__ == "__main__":
    asyncio.run(debug_one_trade())
