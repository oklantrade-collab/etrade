"""
Verificación Final de Frankfurt.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

sb = get_supabase()

def final_verify():
    print(f"\n{'='*60}")
    print(f"VERIFICACIÓN FINAL DE ESTRUCTURA - {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")

    now = datetime.now(timezone.utc)
    time_threshold = (now - timedelta(minutes=15)).isoformat()

    # --- SNAPSHOT ---
    print("\n[SNAPSHOT] market_snapshot (Ultimas actualizaciones)")
    res1 = sb.table('market_snapshot').select(
        'symbol, structure_15m, structure_4h, updated_at'
    ).neq('symbol', 'TEST').order('updated_at', desc=True).execute()
    
    if res1.data:
        for r in res1.data:
            print(f"{r['symbol']:<10} | 15M: {r['structure_15m']:<10} | 4H: {r['structure_4h']:<10} | {r['updated_at']}")
    else:
        print("No data.")

    # --- LOGS ---
    print("\n[LOGS] Ultimos logs de STRUCTURE / v4_scheduler")
    res2 = sb.table('system_logs').select(
        'module, message, created_at'
    ).in_('module', ['STRUCTURE', 'v4_scheduler', 'SNAPSHOT']).gte('created_at', time_threshold).order('created_at', desc=True).limit(20).execute()
    
    if res2.data:
        for r in res2.data:
            print(f"[{r['created_at']}] {r['module']:<15} | {r['message']}")
    else:
        print("No recent logs found.")

if __name__ == "__main__":
    final_verify()
