import asyncio
from app.core.supabase_client import get_supabase

async def add_bb_upper_ascending():
    sb = get_supabase()
    
    # Add variable
    var = {
        "id": 61, # Assuming 61 is available, or we just rely on sequence if we don't pass id? Wait, I will just omit ID so Supabase auto-increments, but let's check what the last ID was. It was 60. Let's just use 61.
        "name": "bb_upper_ascending_15m",
        "description": "Banda superior BB asciende en velas actuales",
        "source_field": "bb_upper_ascending_15m",
        "category": "combined",
        "enabled": True
    }
    try:
        sb.table('strategy_variables').upsert(var).execute()
        print(f"Variable '{var['name']}' upserted.")
    except Exception as e:
        print(f"Error upserting variable {var['name']}: {e}")

    # Add condition
    cond = {
        "id": 71, # Assuming 71 is available (last was 70)
        "name": "BB Upper Ascendiendo",
        "variable_id": 61,
        "operator": "==",
        "value_type": "literal",
        "value_literal": 1,
        "enabled": True
    }
    try:
        sb.table('strategy_conditions').upsert(cond).execute()
        print(f"Condition '{cond['name']}' upserted.")
    except Exception as e:
        print(f"Error upserting condition {cond['name']}: {e}")

if __name__ == "__main__":
    asyncio.run(add_bb_upper_ascending())
