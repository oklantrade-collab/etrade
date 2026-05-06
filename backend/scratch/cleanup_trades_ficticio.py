import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def cleanup_trades():
    sb = get_supabase()
    # Identificar trades ficticios en la tabla 'trades' (precio > 4000 para XAUUSD)
    res = sb.table('trades').select('*').eq('symbol', 'XAUUSD').gte('entry_price', 4000).execute()
    count = len(res.data or [])
    print(f"Encontrados {count} trades ficticios de XAUUSD en la tabla 'trades'.")
    
    if count > 0:
        ids = [p['id'] for p in res.data]
        sb.table('trades').delete().in_('id', ids).execute()
        print(f"Eliminados {count} trades de 'trades'.")

if __name__ == "__main__":
    asyncio.run(cleanup_trades())
