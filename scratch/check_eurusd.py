import os
import sys
import dotenv

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

pos_res = sb.table("forex_positions").select("*").eq("symbol", "EURUSD").order("opened_at", desc=True).limit(5).execute()
print("EURUSD POSITIONS IN SUPABASE:")
for row in pos_res.data or []:
    print(row)
