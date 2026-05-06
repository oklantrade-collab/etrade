import asyncio
from app.core.supabase_client import get_supabase

async def cleanup():
    sb = get_supabase()
    # Identificar posiciones ficticias (precio > 4000 para XAUUSD)
    res = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').gte('entry_price', 4000).execute()
    count = len(res.data or [])
    print(f"Encontradas {count} posiciones ficticias de XAUUSD.")
    
    if count > 0:
        ids = [p['id'] for p in res.data]
        # Eliminar de forex_positions
        sb.table('forex_positions').delete().in_('id', ids).execute()
        print(f"Eliminadas {count} posiciones de forex_positions.")
        
    # También limpiar market_candles erróneos
    res_candles = sb.table('market_candles').select('*').eq('symbol', 'XAUUSD').gte('close', 4000).execute()
    count_candles = len(res_candles.data or [])
    print(f"Encontrados {count_candles} velas ficticias de XAUUSD.")
    if count_candles > 0:
        sb.table('market_candles').delete().eq('symbol', 'XAUUSD').gte('close', 4000).execute()
        print(f"Eliminadas {count_candles} velas de market_candles.")

if __name__ == "__main__":
    asyncio.run(cleanup())
