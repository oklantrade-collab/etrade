import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def cleanup_more():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').gte('entry_price', 3000).execute()
    count = len(res.data or [])
    print(f"Encontrados {count} trades de XAUUSD > 3000.")
    if count > 0:
        ids = [p['id'] for p in res.data]
        sb.table('forex_positions').delete().in_('id', ids).execute()
        print(f"Eliminados {count} trades de forex_positions.")

if __name__ == "__main__":
    asyncio.run(cleanup_more())
