import os
import sys
import dotenv

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res = sb.table("trading_config").select("*").eq("id", 1).maybe_single().execute()
print("TRADING CONFIG SAFETY BLOCKS:")
if res and res.data:
    reg = res.data.get("regime_params", {})
    print("safety_blocked_crypto:", reg.get("safety_blocked_crypto"))
    print("safety_blocked_forex:", reg.get("safety_blocked_forex"))
    print("safety_checked_at:", reg.get("safety_checked_at"))
