import asyncio
from app.core.supabase_client import get_supabase

async def debug_ada():
    supabase = get_supabase()
    symbol = "ADA/USDT"
    print(f"Debugging {symbol} around 07:30 - 07:45...")
    
    # 07:30 AM EST to 08:00 AM EST is 12:30 to 13:00 UTC
    evals = supabase.table("strategy_evaluations").select("*")\
        .eq("symbol", symbol)\
        .in_("rule_code", ["Aa21", "AaHot"])\
        .gte("created_at", "2026-05-28T12:00:00Z")\
        .lte("created_at", "2026-05-28T13:30:00Z")\
        .execute()
        
    print(f"Found {len(evals.data)} evaluations")
    for ev in evals.data:
        print(f"\nTime: {ev['created_at']}, Rule: {ev['rule_code']}, Triggered: {ev['triggered']}")
        if not ev['triggered']:
            print(f"  Reason: {ev.get('failure_reason')}")
            # Print the unmet conditions
            if ev.get('conditions_met'):
                for k, v in ev['conditions_met'].items():
                    if not v:
                        print(f"    Failed condition: {k}")

if __name__ == "__main__":
    asyncio.run(debug_ada())
