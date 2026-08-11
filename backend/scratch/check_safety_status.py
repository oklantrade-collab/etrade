import sys
import os
from datetime import datetime, timezone
sys.path.append('c:/Fuentes/eTrade/backend')

from app.core.supabase_client import get_supabase

def check_safety():
    sb = get_supabase()
    
    print("="*60)
    print("=== INSPECCIÓN DE SAFETY MANAGER & WORKER HEARTBEATS ===")
    print("="*60)
    
    # 1. Check worker_heartbeats
    try:
        hb = sb.table('worker_heartbeats').select('*').execute()
        print(f"\n1. WORKER HEARTBEATS (Total: {len(hb.data or [])}):")
        for h in (hb.data or []):
            print(f"   Worker: {h.get('worker_id')} | Last Seen: {h.get('last_seen')} | Status: {h.get('status')}")
    except Exception as e:
        print("Error reading worker_heartbeats:", e)

    # 2. Check safety_locks
    try:
        locks = sb.table('safety_locks').select('*').execute()
        print(f"\n2. SAFETY LOCKS (Total: {len(locks.data or [])}):")
        for l in (locks.data or []):
            print(f"   Market: {l.get('market_type')} | Locked: {l.get('is_locked')} | Reason: {l.get('reason')} | Updated: {l.get('updated_at')}")
    except Exception as e:
        print("Error reading safety_locks:", e)

    # 3. Check trading_config safety fields
    try:
        cfg = sb.table('trading_config').select('id, emergency_action, emergency_enabled').eq('id', 1).execute()
        print(f"\n3. TRADING CONFIG EMERGENCY STATUS:")
        print(f"   {cfg.data}")
    except Exception as e:
        print("Error reading trading_config:", e)

if __name__ == "__main__":
    check_safety()
