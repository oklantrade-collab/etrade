import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    res = sb.table("stocks_rules").select("*").eq("rule_code", "S05").execute()
    if res.data:
        rule = res.data[0]
        allowed = rule.get("movements_allowed", [])
        if "descending" in allowed:
            allowed.remove("descending")
            sb.table("stocks_rules").update({"movements_allowed": allowed}).eq("rule_code", "S05").execute()
            print("Rule S05 updated: removed 'descending' from movements_allowed.")
            print(f"New movements_allowed: {allowed}")
        else:
            print("Rule S05 already fixed.")
    else:
        print("Rule S05 not found.")

if __name__ == "__main__":
    main()
