import asyncio
from app.core.supabase_client import get_supabase

async def migrate():
    sb = get_supabase()

    # IDs verified from previous check:
    # ID 17 -> fibonacci_zone (fib_zone)
    # ID 24 -> upper_6
    # ID 30 -> lower_6

    # 1. Update Conditions to use fibonacci_zone (ID 17) and value 6
    conditions = [
        {
            "id": 59,
            "name": "Precio en zona extrema LOWER_6",
            "variable_id": 17, # fibonacci_zone
            "operator": "<=",
            "value_literal": -6,
            "value_type": "literal",
            "enabled": True
        },
        {
            "id": 60,
            "name": "Precio en zona extrema UPPER_6",
            "variable_id": 17, # fibonacci_zone
            "operator": ">=",
            "value_literal": 6,
            "value_type": "literal",
            "enabled": True
        }
    ]
    for c in conditions:
        sb.table('strategy_conditions').upsert(c).execute()

    # Reload engine to pick up condition changes
    from app.strategy.strategy_engine import StrategyEngine
    engine = StrategyEngine.get_instance(sb)
    await engine.reload()

    print("Migration completed: conditions 59 and 60 updated to strictly Level 6.")

if __name__ == "__main__":
    asyncio.run(migrate())
