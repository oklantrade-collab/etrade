import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

async def check_and_add():
    sb = get_supabase()
    
    # Check max ID for variables
    res = sb.table('strategy_variables').select('id').order('id', desc=True).limit(1).execute()
    next_var_id = (res.data[0]['id'] + 1) if res.data else 1
    
    # Check max ID for conditions
    res_cond = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
    next_cond_id = (res_cond.data[0]['id'] + 1) if res_cond.data else 1
    
    variables = [
        {
            "id": next_var_id,
            "name": "low_below_bb_lower_90_15m",
            "source_field": "low_below_bb_lower_90_15m",
            "category": "combined",
            "enabled": True,
            "timeframes": ["15m"],
            "description": "El LOW alcanza el 90% de la distancia entre BASIS y BANDA INFERIOR en 15M"
        },
        {
            "id": next_var_id + 1,
            "name": "high_above_bb_upper_90_15m",
            "source_field": "high_above_bb_upper_90_15m",
            "category": "combined",
            "enabled": True,
            "timeframes": ["15m"],
            "description": "El HIGH alcanza el 90% de la distancia entre BASIS y BANDA SUPERIOR en 15M"
        }
    ]
    
    for v in variables:
        sb.table('strategy_variables').upsert(v).execute()
        print(f"Inserted variable: {v['name']} with ID {v['id']}")
        
    conditions = [
        {
            "id": next_cond_id,
            "name": "LOW < BOLLINGER INF 90% - 15M",
            "variable_id": variables[0]["id"],
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "timeframe": "15m",
            "description": "Vela 15m alcanza el 90% de cercanía a Bollinger Inferior",
            "enabled": True
        },
        {
            "id": next_cond_id + 1,
            "name": "HIGH > BOLLINGER SUP 90% - 15M",
            "variable_id": variables[1]["id"],
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "timeframe": "15m",
            "description": "Vela 15m alcanza el 90% de cercanía a Bollinger Superior",
            "enabled": True
        }
    ]
    
    for c in conditions:
        sb.table('strategy_conditions').upsert(c).execute()
        print(f"Inserted condition: {c['name']} with ID {c['id']}")

if __name__ == "__main__":
    asyncio.run(check_and_add())
