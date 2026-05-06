import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_rules_columns():
    sb = get_supabase()
    res = sb.table("stocks_rules").select("*").in_("rule_code", ["PRO_CANDLE_SELL", "HOT_CANDLE_SELL"]).execute()
    for rule in res.data:
        print(f"Rule: {rule['rule_code']}")
        print(f"SIPV Required: {rule.get('sipv_required')}, SIPV Signal: {rule.get('sipv_signal')}")
        print(f"Pine Required: {rule.get('pine_required')}, Pine Signal: {rule.get('pine_signal')}")
        print(f"Fib Trigger: {rule.get('fib_trigger')}")

if __name__ == "__main__":
    asyncio.run(check_rules_columns())
