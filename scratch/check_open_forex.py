import os
import sys
import dotenv

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res_open = sb.table("forex_positions").select("*").eq("status", "open").execute()
print("OPEN POSITIONS IN FOREX_POSITIONS DB TABLE:")
for p in res_open.data or []:
    print(f"ID: {p['id']}, Symbol: {p['symbol']}, OpenedAt: {p['opened_at']}, Status: {p['status']}")
