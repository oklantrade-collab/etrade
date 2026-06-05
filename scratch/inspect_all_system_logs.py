import os
import sys
from datetime import datetime, timezone, timedelta

# Agregar backend al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    # Consultar logs de las últimas 3 horas
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    print(f"--- LOGS DEL SISTEMA DESDE {cutoff} ---")
    
    res = sb.table('system_logs') \
        .select('*') \
        .gte('created_at', cutoff) \
        .order('created_at', desc=False) \
        .execute()
        
    logs = res.data or []
    if not logs:
        print("No hay logs en las últimas 3 horas.")
        return
        
    for l in logs:
        print(f"{l.get('created_at')} | {l.get('level')} | {l.get('message')} | Context: {l.get('context')}")

if __name__ == '__main__':
    main()
