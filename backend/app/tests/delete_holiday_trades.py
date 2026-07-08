import sys
import os
import asyncio
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.core.supabase_client import get_supabase

async def delete_zero_pnl_trades():
    sb = get_supabase()
    print("Buscando posiciones de Stocks cerradas hoy (2026-07-03) con PNL = 0...")
    
    # Obtener todas las posiciones cerradas de stocks
    res = sb.table("stocks_positions").select("*").eq("status", "closed").execute()
    positions = res.data or []
    
    count_deleted = 0
    for pos in positions:
        opened_at_str = pos.get('opened_at', '') or pos.get('updated_at', '')
        pnl = float(pos.get('realized_pnl') or 0.0)
        
        # Si fue creada hoy y el PnL es 0
        if "2026-07-03" in opened_at_str and abs(pnl) < 0.0001:
            pos_id = pos['id']
            symbol = pos['ticker']
            print(f"Borrando posicion ID {pos_id} de {symbol}...")
            
            # 1. Borrar órdenes relacionadas
            sb.table("orders").delete().eq("position_id", pos_id).execute()
            
            # 2. Borrar órdenes pendientes si las hay
            sb.table("pending_orders").delete().eq("position_id", pos_id).execute()
            
            # 3. Borrar la posición
            sb.table("stocks_positions").delete().eq("id", pos_id).execute()
            count_deleted += 1
            
    print(f"Total de posiciones eliminadas: {count_deleted}")

if __name__ == "__main__":
    asyncio.run(delete_zero_pnl_trades())
