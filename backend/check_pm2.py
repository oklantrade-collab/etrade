import sys
import os
import asyncio

print("--- DIAGNOSTIC START ---")
print(f"Python Executable: {sys.executable}")
print(f"Current Path: {os.getcwd()}")
print("--- TESTING IMPORTS ---")
try:
    import pandas as pd
    print("[OK] pandas imported")
except Exception as e:
    print(f"[ERROR] pandas FAILED: {e}")

try:
    from app.workers.stocks_scheduler import start_stocks_scheduler
    print("[OK] stocks_scheduler components imported")
except Exception as e:
    print(f"[ERROR] stocks_scheduler FAILED: {e}")

try:
    from app.stocks.decision_engine import DecisionEngine
    print("[OK] DecisionEngine imported")
    engine = DecisionEngine()
    print("[OK] DecisionEngine initialized")
except Exception as e:
    print(f"[ERROR] DecisionEngine FAILED: {e}")

print("--- TESTING SUPABASE ---")
try:
    from app.core.supabase_client import get_supabase
    sb = get_supabase()
    res = sb.table("stocks_config").select("key").limit(1).execute()
    print(f"[OK] Supabase connected (data: {len(res.data) if res.data else 0} rows)")
except Exception as e:
    print(f"[ERROR] Supabase FAILED: {e}")

print("--- DIAGNOSTIC END ---")
