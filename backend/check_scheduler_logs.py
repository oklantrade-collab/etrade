"""
Revisión de logs del scheduler.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

sb = get_supabase()

def check():
    print(f"\nLOGS DE SCHEDULER DESPUÉS DE 03:00 UTC")
    time_limit = "2026-03-25T03:00:00+00:00"
    res = sb.table('system_logs').select(
        'module, message, created_at'
    ).gte('created_at', time_limit).order('created_at', desc=True).limit(100).execute()
    
    if res.data:
        for r in res.data:
            print(f"[{r['created_at']}] {r['module']:<15} | {r['message']}")
    else:
        print("No se encontraron logs.")

if __name__ == "__main__":
    check()
