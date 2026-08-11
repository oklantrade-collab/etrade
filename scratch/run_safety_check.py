import os
import sys
import dotenv
import asyncio

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.safety_manager import check_subprocesses_safety
from app.core.supabase_client import get_supabase

async def main():
    sb = get_supabase()
    res = await check_subprocesses_safety(sb)
    print("SUBPROCESSES SAFETY CHECK RESULT:")
    print(res)

    cfg = sb.table("trading_config").select("*").eq("id", 1).maybe_single().execute()
    reg = cfg.data.get("regime_params", {}) if cfg and cfg.data else {}
    print(f"NEW safety_blocked_crypto: {reg.get('safety_blocked_crypto')}")
    print(f"NEW safety_blocked_forex: {reg.get('safety_blocked_forex')}")

asyncio.run(main())
