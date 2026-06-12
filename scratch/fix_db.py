import asyncio
from app.core.supabase_client import get_supabase

async def fix():
    sb = get_supabase()
    sb.table('forex_positions').update({'pnl_usd': 0.0112}).eq('id', '829e6ff9-feb9-4b75-a30a-2ef430dfe2ec').execute()
    sb.table('forex_positions').update({'pnl_usd': 0.1136}).eq('id', '7277ca79-31dc-414a-ac18-a7d45d3533f9').execute()
    print('DB fixed.')

if __name__ == "__main__":
    asyncio.run(fix())
