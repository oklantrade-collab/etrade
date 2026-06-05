import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    res = sb.table("stocks_rules").select("*").eq("rule_code", "S05").execute()
    for r in res.data:
        print(r)

if __name__ == "__main__":
    main()
