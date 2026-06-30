import asyncio
import sys

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
            "name": "low_below_bb_lower_1h",
            "source_field": "low_below_bb_lower_1h",
            "category": "combined",
            "enabled": True,
            "timeframes": ["1h"],
            "description": "El LOW cruza o esta debajo de la banda inferior de Bollinger en 1H"
        },
        {
            "id": next_var_id + 1,
            "name": "bb_lower_ascending_1h",
            "source_field": "bb_lower_ascending_1h",
            "category": "combined",
            "enabled": True,
            "timeframes": ["1h"],
            "description": "Banda inferior de Bollinger ascendente en vela actual y anterior de 1H"
        }
    ]
    
    for v in variables:
        sb.table('strategy_variables').upsert(v).execute()
        print(f"Inserted variable: {v['name']} with ID {v['id']}")
        
    conditions = [
        {
            "id": next_cond_id,
            "name": "LOW < BANDA INF BOLL 1H",
            "variable_id": variables[0]["id"],
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "timeframe": "1h",
            "description": "LOW menor a Banda Inferior Bollinger 1H",
            "enabled": True
        },
        {
            "id": next_cond_id + 1,
            "name": "Banda Inferior Bollinger ASC (act y ant) 1H",
            "variable_id": variables[1]["id"],
            "operator": "==",
            "value_type": "literal",
            "value_literal": 1,
            "timeframe": "1h",
            "description": "Banda Inferior Bollinger ascendente en 1H (2 velas)",
            "enabled": True
        }
    ]
    
    for c in conditions:
        sb.table('strategy_conditions').upsert(c).execute()
        print(f"Inserted condition: {c['name']} with ID {c['id']}")

if __name__ == "__main__":
    asyncio.run(check_and_add())
