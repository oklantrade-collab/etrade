
import asyncio
import os
import sys
from datetime import datetime, timezone
from app.core.supabase_client import get_supabase

# Asegurar que el path sea correcto para importar app
sys.path.append(os.getcwd())

async def monitor_audit():
    sb = get_supabase()
    print("--- AUDITORÍA DE PROTECCIÓN DE CAPITAL INICIADA ---")
    print(f"Hora de inicio: {datetime.now(timezone.utc).isoformat()}")
    print("Esperando señales en Forex y Crypto para verificar SL/Trailing...")
    
    known_positions = {} # id -> last_sl
    
    while True:
        try:
            # 1. Consultar Forex
            fx_res = sb.table('forex_positions').select('id, symbol, side, entry_price, sl_price, status, created_at').eq('status', 'open').execute()
            # 2. Consultar Crypto
            cr_res = sb.table('positions').select('id, symbol, side, entry_price, sl_price, status, opened_at').eq('status', 'open').execute()
            
            all_open = (fx_res.data or []) + (cr_res.data or [])
            
            # Detectar cierres
            current_ids = {p['id'] for p in all_open}
            closed_ids = set(known_positions.keys()) - current_ids
            for cid in closed_ids:
                print(f"✅ POSICIÓN CERRADA: ID {cid} (Ver historial para razón de salida)")
                del known_positions[cid]

            for p in all_open:
                pid = p['id']
                symbol = p['symbol']
                current_sl = p['sl_price']
                
                if pid not in known_positions:
                    print(f"🚀 [NEW] {symbol} {p['side']} | Entry: {p['entry_price']} | SL: {current_sl}")
                    known_positions[pid] = current_sl
                else:
                    # Verificar si el SL se movió (Trailing Stop / Break-Even)
                    if current_sl != known_positions[pid]:
                        print(f"🛡️ [PROTECTION] {symbol}: SL movido de {known_positions[pid]} a {current_sl}")
                        known_positions[pid] = current_sl
            
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error en monitor: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(monitor_audit())
