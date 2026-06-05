import os
import sys
from datetime import datetime, timezone

# Agregar backend al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    print("--- BUSCANDO LOGS DE BTCUSDT DESDE LAS 19:00 UTC ---")
    
    res = sb.table('system_logs') \
        .select('*') \
        .gte('created_at', '2026-05-30T19:00:00+00:00') \
        .order('created_at', desc=False) \
        .execute()
        
    logs = res.data or []
    found = False
    for l in logs:
        msg = l.get('message', '')
        if 'btcusdt' in msg.lower() or 'btc' in msg.lower():
            print(f"{l.get('created_at')} | {l.get('level')} | {msg} | Context: {l.get('context')}")
            found = True
            
    if not found:
        print("No se encontraron logs específicos para BTCUSDT.")

if __name__ == '__main__':
    main()
