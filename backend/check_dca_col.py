import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_col():
    sb = get_supabase()
    try:
        res = sb.table("positions").select("dca_executed").limit(1).execute()
        print("[OK] dca_executed column exists")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_col()
