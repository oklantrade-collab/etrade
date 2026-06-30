import asyncio
import sys

from app.core.supabase_client import get_supabase

async def add_rsi_condition():
    sb = get_supabase()
    
    # Check max ID for conditions
    res_cond = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
    next_cond_id = (res_cond.data[0]['id'] + 1) if res_cond.data else 1
    
    # The variable ID for RSI is 112 based on previous checks
    
    c = {
        "id": next_cond_id,
        "name": "(rsi < 20)",
        "variable_id": 112,
        "operator": "<",
        "value_type": "literal",
        "value_literal": 20,
        "timeframe": None, # Dynamic timeframe based on strategy
        "description": "RSI menor a 20 en la temporalidad de la estrategia",
        "enabled": True
    }
    
    sb.table('strategy_conditions').upsert(c).execute()
    print(f"Inserted condition: {c['name']} with ID {c['id']}")

if __name__ == "__main__":
    asyncio.run(add_rsi_condition())
