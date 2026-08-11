import os
import sys
import dotenv

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res = sb.table("pending_orders").select("*").eq("status", "pending").execute()
print("CURRENT PENDING ORDERS IN SUPABASE (status=='pending'):")
print(res.data)
