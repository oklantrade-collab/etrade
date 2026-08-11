import os
import sys
import dotenv

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res = sb.table("forex_positions").select("*").order("opened_at", desc=True).limit(5).execute()
print("RECENT FOREX POSITIONS IN SUPABASE:")
for p in res.data or []:
    print(p)
