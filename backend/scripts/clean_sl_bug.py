import sys
import os
import asyncio
from datetime import datetime

# Añadir el raíz para que entienda las importaciones
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.supabase_client import get_supabase

async def clean_bug_trades():
    print("Iniciando limpieza de base de datos...")
    sb = get_supabase()
    date_limit = '2026-04-06T00:00:00Z'
    
    # 1. Borrar de paper_trades
    res_pt = sb.table('paper_trades').delete().eq('close_reason', 'sl').gte('closed_at', date_limit).execute()
    count_pt = len(res_pt.data) if res_pt.data else 0
    print(f"Borrados {count_pt} trades erróneos de paper_trades.")
    
    # 2. Borrar de positions
    res_pos = sb.table('positions').delete().eq('status', 'closed').eq('close_reason', 'sl').gte('closed_at', date_limit).execute()
    count_pos = len(res_pos.data) if res_pos.data else 0
    print(f"Boradas {count_pos} posiciones erróneas de positions.")
    
    # 3. Borrar de orders (como un plus, borrar las relativas a esas posiciones que terminaron en sl_hit)
    res_ord = sb.table('orders').delete().eq('status', 'sl_hit').gte('closed_at', date_limit).execute()
    count_ord = len(res_ord.data) if res_ord.data else 0
    print(f"Boradas {count_ord} orders vinculadas.")
    
    print("Limpieza de la base de datos completada!")

if __name__ == '__main__':
    asyncio.run(clean_bug_trades())
