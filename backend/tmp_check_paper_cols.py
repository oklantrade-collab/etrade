from app.core.supabase_client import get_supabase
import asyncio

async def check_paper_trades_cols():
    sb = get_supabase()
    res = sb.table('paper_trades').select('*').limit(1).execute()
    print(res.data[0].keys())

if __name__ == "__main__":
    asyncio.run(check_paper_trades_cols())
