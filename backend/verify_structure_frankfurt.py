"""
Verificación de la implementación de Estructura de Mercado en Frankfurt.
Ejecuta las 3 consultas mediante la API de Supabase.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

sb = get_supabase()

def verify():
    print(f"\n{'='*60}")
    print(f"VERIFICACIÓN DE ESTRUCTURA EN FRANKFURT - {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")

    # --- QUERY 1: MARKET SNAPSHOT ---
    print("\nQUERY 1: market_snapshot Columns")
    res1 = sb.table('market_snapshot').select(
        'symbol, structure_15m, allow_long_15m, allow_short_15m, reverse_signal_15m, structure_4h, allow_long_4h, allow_short_4h, reverse_signal_4h, updated_at'
    ).neq('symbol', 'TEST').order('symbol').execute()
    
    if res1.data:
        print(f"{'SYMBOL':<10} | {'S_15M':<10} | {'S_4H':<10} | {'AL_15M':<6} | {'AL_4H':<6} | {'REV_15M':<7} | {'UPDATED_AT'}")
        print("-" * 100)
        for r in res1.data:
            print(f"{r['symbol']:<10} | {str(r['structure_15m']):<10} | {str(r['structure_4h']):<10} | {str(r['allow_long_15m']):<6} | {str(r['allow_long_4h']):<6} | {str(r['reverse_signal_15m']):<7} | {r['updated_at']}")
    else:
        print("No hay datos en market_snapshot")

    # --- QUERY 2: SYSTEM LOGS ---
    print("\nQUERY 2: Structure Logs (Last 60 mins)")
    time_threshold = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
    res2 = sb.table('system_logs').select(
        'module, message, created_at'
    ).in_('module', ['STRUCTURE', 'STRUCTURE_5M', 'STRUCTURE_15M']).gte('created_at', time_threshold).order('created_at', desc=True).limit(20).execute()
    
    if res2.data:
        for r in res2.data:
            print(f"[{r['created_at']}] {r['module']:<15} | {r['message']}")
    else:
        print("No se encontraron logs de STRUCTURE recientes.")

    # --- QUERY 3: PILOT DIAGNOSTICS GROUP BY ---
    print("\nQUERY 3: Frankfurt Activity (Last 60 mins)")
    res3 = sb.table('pilot_diagnostics').select(
        'symbol, cycle_type, timestamp'
    ).gte('timestamp', time_threshold).execute()
    
    if res3.data:
        counts = {}
        lasts = {}
        for r in res3.data:
            key = (r['symbol'], r['cycle_type'])
            counts[key] = counts.get(key, 0) + 1
            if key not in lasts or r['timestamp'] > lasts[key]:
                lasts[key] = r['timestamp']
        
        sorted_keys = sorted(counts.keys())
        print(f"{'SYMBOL':<10} | {'CYCLE':<6} | {'COUNT':<5} | {'LAST_TIMESTAMP'}")
        print("-" * 60)
        for key in sorted_keys:
            print(f"{key[0]:<10} | {key[1]:<6} | {counts[key]:<5} | {lasts[key]}")
    else:
        print("No se encontraron diagnósticos recientes.")

if __name__ == "__main__":
    verify()
