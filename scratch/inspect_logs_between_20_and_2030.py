import os
import sys

# Agregar backend al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    print("--- LOGS DEL SISTEMA ENTRE 20:00 Y 20:30 UTC ---")
    
    res = sb.table('system_logs') \
        .select('*') \
        .gte('created_at', '2026-05-30T20:00:00+00:00') \
        .lte('created_at', '2026-05-30T20:30:00+00:00') \
        .order('created_at', desc=False) \
        .execute()
        
    logs = res.data or []
    if not logs:
        print("No se encontraron logs en este periodo.")
        return
        
    for l in logs:
        print(f"{l.get('created_at')} | {l.get('level')} | {l.get('message')} | Context: {l.get('context')}")

if __name__ == '__main__':
    main()
