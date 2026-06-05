import os
import sys
from datetime import datetime, timezone

# Agregar backend al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    ids = ['d54f58e2-73aa-4272-8f34-8e7aed3c868a', 'd24a3768-e38f-4063-b27e-5985f5f3ef0f']
    print("--- REPARANDO POSICIONES NULAS EN DB ---")
    
    for pid in ids:
        p_res = sb.table('positions').select('*').eq('id', pid).execute()
        if p_res.data:
            p = p_res.data[0]
            opened_at_str = p.get('opened_at')
            
            # Vamos a poner como closed_at la fecha de apertura + 5 minutos
            try:
                opened_at_dt = datetime.fromisoformat(opened_at_str.replace('Z', '+00:00'))
                closed_at_dt = opened_at_dt
                closed_at_str = closed_at_dt.isoformat()
            except Exception:
                closed_at_str = opened_at_str # fallback
                
            entry = float(p.get('entry_price') or 0)
            qty = float(p.get('size') or 0)
            
            # PNL realizado es 0.00 porque el precio de entrada y salida coincide ($0.2371 y $2026.83)
            realized_pnl = 0.0
            
            update_data = {
                'closed_at': closed_at_str,
                'close_reason': 'MANUAL_DB_EDIT',
                'realized_pnl': realized_pnl,
                'realized_pnl_pct': 0.0,
                'current_price': entry
            }
            
            upd_res = sb.table('positions').update(update_data).eq('id', pid).execute()
            if upd_res.data:
                print(f"[SUCCESS] Posición {pid} ({p.get('symbol')}) reparada exitosamente.")
                print(f"  Closed At: {closed_at_str} | Reason: MANUAL_DB_EDIT | PNL: {realized_pnl}")
            else:
                print(f"[FAIL] No se pudo actualizar la posición {pid}.")
        else:
            print(f"[WARN] Posición {pid} no encontrada en DB.")
            
if __name__ == '__main__':
    main()
