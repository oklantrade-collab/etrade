import sys
import os
from datetime import datetime, timezone
sys.path.append('c:/Fuentes/eTrade/backend')

from app.core.supabase_client import get_supabase
from app.core.safety_manager import register_heartbeat, set_forex_safety_block, set_crypto_safety_block, update_db_safety_block

def unlock_safety():
    sb = get_supabase()
    
    print("="*60)
    print("=== DESBLOQUEANDO SAFETY LOCKS Y ACTUALIZANDO HEARTBEATS ===")
    print("="*60)
    
    # 1. Reset memory locks in safety_manager
    set_forex_safety_block(False)
    set_crypto_safety_block(False)
    
    # 2. Reset DB locks in trading_config
    update_db_safety_block('forex_futures', False)
    update_db_safety_block('crypto_futures', False)
    
    # 3. Register heartbeats for all core workers
    register_heartbeat('position_monitor')
    register_heartbeat('crypto_scheduler')
    register_heartbeat('forex_worker')
    register_heartbeat('scheduler')
    
    print("Heartbeats registrados exitosamente para: position_monitor, crypto_scheduler, forex_worker, scheduler.")
    
    # 4. Verify trading_config regime_params
    res = sb.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
    if res and res.data:
        params = res.data.get('regime_params') or {}
        print("\nEstado actual de regime_params en DB:")
        print(f"  - safety_blocked_forex: {params.get('safety_blocked_forex')}")
        print(f"  - safety_blocked_crypto: {params.get('safety_blocked_crypto')}")
        print(f"  - safety_checked_at: {params.get('safety_checked_at')}")

if __name__ == "__main__":
    unlock_safety()
