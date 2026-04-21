
import os
import sys
from datetime import datetime, timezone

# Asegurar que el path del backend esté disponible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

def cleanup_symbol(symbol, limit=4):
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('symbol', symbol).eq('status', 'open').order('opened_at', desc=False).execute()
    pos = res.data or []
    
    if len(pos) > limit:
        # Mantener los 4 más antiguos, cerrar el resto
        excess = pos[limit:]
        print(f"Cerrando {len(excess)} posiciones de {symbol}")
        for p in excess:
            sb.table('forex_positions').update({
                'status': 'closed', 
                'close_reason': 'excess_cleanup', 
                'closed_at': datetime.now(timezone.utc).isoformat()
            }).eq('id', p['id']).execute()
    else:
        print(f"No hay exceso en {symbol} ({len(pos)}/{limit})")

if __name__ == "__main__":
    cleanup_symbol('GBPUSD', 4)
    cleanup_symbol('USDJPY', 4)
    cleanup_symbol('EURUSD', 4)
