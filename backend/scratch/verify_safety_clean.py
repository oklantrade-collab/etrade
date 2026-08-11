import sys
import os
import asyncio
sys.path.append('c:/Fuentes/eTrade/backend')

from app.core.supabase_client import get_supabase
from app.core.safety_manager import check_subprocesses_safety, is_forex_safety_blocked, is_crypto_safety_blocked, register_heartbeat

async def verify():
    sb = get_supabase()
    
    # Touch heartbeats to simulate fresh active workers
    register_heartbeat('position_monitor')
    register_heartbeat('crypto_scheduler')
    register_heartbeat('forex_worker')
    register_heartbeat('scheduler')
    
    res = await check_subprocesses_safety(sb)
    print("=== RESULTADO DEL SAFETY CHECK EN TIEMPO REAL ===")
    print("Forex Bloqueado:", res.get('forex_blocked'), "| En memoria:", is_forex_safety_blocked())
    print("Crypto Bloqueado:", res.get('crypto_blocked'), "| En memoria:", is_crypto_safety_blocked())

if __name__ == "__main__":
    asyncio.run(verify())
