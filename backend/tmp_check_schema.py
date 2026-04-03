import asyncio
from app.core.supabase_client import get_supabase

async def check_schema():
    sb = get_supabase()
    
    # Strategy Rules V2
    rule = sb.table('strategy_rules_v2').select('*').limit(1).execute()
    print("--- Strategy Rules V2 Columns ---")
    if rule.data:
        print(rule.data[0].keys())

    # Strategy Conditions
    cond = sb.table('strategy_conditions').select('*').limit(1).execute()
    print("\n--- Strategy Conditions Columns ---")
    if cond.data:
        print(cond.data[0].keys())

if __name__ == "__main__":
    asyncio.run(check_schema())
