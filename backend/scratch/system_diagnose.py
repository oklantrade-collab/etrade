
from app.core.supabase_client import get_supabase
import pandas as pd
from datetime import datetime, timezone

def diagnose_state():
    sb = get_supabase()
    
    print("--- DIAGNÓSTICO DE POSICIONES ---")
    pos_res = sb.table('positions').select('*').eq('status', 'open').execute()
    positions = pos_res.data or []
    
    if not positions:
        print("No hay posiciones abiertas.")
    else:
        df = pd.DataFrame(positions)
        counts = df.groupby('symbol').size()
        print(f"Total de posiciones abiertas: {len(positions)}")
        print("Conteo por símbolo:")
        print(counts)
        
        excess = counts[counts > 4]
        if not excess.empty:
            print("\n⚠️ ALERTA: Símbolos con más de 4 posiciones:")
            print(excess)
        
        # Check for same entry price
        for symbol, group in df.groupby('symbol'):
            prices = group['avg_entry_price'].tolist()
            if len(prices) != len(set(prices)):
                print(f"⚠️ ALERTA: {symbol} tiene posiciones con precios duplicados: {prices}")

    print("\n--- DIAGNÓSTICO DE SNAPSHOT (NUEVAS COLUMNAS) ---")
    snap_res = sb.table('market_snapshot').select('symbol, symbol_state, waiting_cycles, flip_pending').limit(10).execute()
    snaps = snap_res.data or []
    if snaps:
        print(pd.DataFrame(snaps))
    else:
        print("No se encontraron registros en market_snapshot.")

if __name__ == "__main__":
    diagnose_state()
