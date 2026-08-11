import os
import sys
import dotenv

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res = sb.table("trading_config").select("id, regime_params").execute()
print("TRADING_CONFIG DATA:")
print(res.data)
