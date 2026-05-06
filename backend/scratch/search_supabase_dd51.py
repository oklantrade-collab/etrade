import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def search_supabase():
    sb = get_supabase()
    tables = ["trading_rules", "strategy_rules_v2", "pending_orders", "bot_global_state", "positions"]
    for t in tables:
        try:
            # Check for column rule_code
            res = sb.table(t).select("*").ilike("rule_code", "%Dd51%").limit(5).execute()
            if res.data:
                print(f"FOUND in table {t} (column rule_code): {len(res.data)} items")
            
            # Check for column name
            res = sb.table(t).select("*").ilike("name", "%Dd51%").limit(5).execute()
            if res.data:
                print(f"FOUND in table {t} (column name): {len(res.data)} items")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(search_supabase())
