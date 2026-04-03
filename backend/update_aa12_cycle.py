import asyncio
from app.core.supabase_client import get_supabase

async def set_aa12_to_15m():
    sb = get_supabase()
    
    print("Updating Aa12 to cycle=15m and priority=0...")
    res = sb.table('strategy_rules_v2').update({
        "cycle": "15m",
        "applicable_cycles": ["15m", "5m"],
        "priority": 0
    }).eq('rule_code', 'Aa12').execute()
    
    if res.data:
        print("Success.")
    else:
        print("Failed to update.")

if __name__ == "__main__":
    asyncio.run(set_aa12_to_15m())
