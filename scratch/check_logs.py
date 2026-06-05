import os
import sys

# Agregar backend al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    print("--- RECENT SYSTEM LOGS ---")
    res = sb.table('system_logs') \
        .select('*') \
        .order('created_at', desc=True) \
        .limit(100) \
        .execute()
        
    logs = res.data or []
    for l in logs:
        msg = l.get('message', '')
        # Imprimir logs que tengan relación con ADA, ETH, manual, positions, etc.
        if any(x in msg.lower() for x in ['ada', 'eth', 'manual', 'position', 'error', 'close', 'reconciliation']):
            print(f"{l.get('created_at')} | {l.get('level')} | {msg} | Context: {l.get('context')}")

if __name__ == '__main__':
    main()
