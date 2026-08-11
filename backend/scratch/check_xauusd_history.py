import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check_history():
    sb = get_supabase()
    
    print("--- 1. BUSCANDO EN signals_log HOY ---")
    try:
        sig = sb.table('signals_log').select('*').order('detected_at', desc=True).limit(15).execute()
        for s in sig.data:
            print(f"[{s.get('detected_at')}] Sym: {s.get('symbol')} | Dir: {s.get('direction')} | Rule: {s.get('rule_code')} | Acted: {s.get('acted_on')} | SkipReason: {s.get('reason_skip')}")
    except Exception as e:
        print("Error signals_log:", e)

    print("\n--- 2. BUSCANDO EN system_logs (Filtro XAUUSD o SHORT o 20:00) ---")
    try:
        logs = sb.table('system_logs').select('*').order('created_at', desc=True).limit(20).execute()
        for l in logs.data:
            print(f"[{l.get('created_at')}] [{l.get('level')}] {l.get('message')[:120]}")
    except Exception as e:
        print("Error system_logs:", e)

if __name__ == "__main__":
    check_history()
