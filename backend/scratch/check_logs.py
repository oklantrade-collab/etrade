import os, sys, json
sys.path.append(os.path.abspath("backend"))
from app.core.supabase_client import get_supabase

sb = get_supabase()
logs = sb.table("system_logs").select("*").ilike("message", "%SPY%").order("created_at", desc=True).limit(10).execute()
for l in logs.data:
    print(f"[{l.get('created_at')}] [{l.get('module')}] [{l.get('level')}]: {l.get('message')}")

print("\n--- RECENT ERRORS IN SYSTEM_LOGS ---")
errs = sb.table("system_logs").select("*").eq("level", "ERROR").order("created_at", desc=True).limit(10).execute()
for l in errs.data:
    print(f"[{l.get('created_at')}] [{l.get('module')}]: {l.get('message')}")
