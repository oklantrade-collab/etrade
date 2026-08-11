import asyncio
from app.core.supabase_client import get_supabase

async def add_close_conditions():
    sb = get_supabase()
    
    # 1. Asegurarnos de tener variable para 'close'
    res_var = sb.table('strategy_variables').select('*').eq('source_field', 'close').execute()
    if not res_var.data:
        res_max_var = sb.table('strategy_variables').select('id').order('id', desc=True).limit(1).execute()
        next_var_id = (res_max_var.data[0]['id'] + 1) if res_max_var.data else 1
        var_close = {
            "id": next_var_id,
            "name": "Close Price",
            "source_field": "close",
            "description": "Precio de cierre de la vela",
            "category": "price"
        }
        sb.table('strategy_variables').insert(var_close).execute()
        close_var_id = next_var_id
        print(f"Created variable 'close' with ID {close_var_id}")
    else:
        close_var_id = res_var.data[0]['id']
        print(f"Found variable 'close' with ID {close_var_id}")

    # 2. Conseguir IDs de ema9 y ema3
    res_ema9 = sb.table('strategy_variables').select('id').eq('source_field', 'ema9').execute()
    ema9_var_id = res_ema9.data[0]['id']
    
    res_ema3 = sb.table('strategy_variables').select('id').eq('source_field', 'ema3').execute()
    ema3_var_id = res_ema3.data[0]['id']

    # 3. Crear las condiciones
    res_cond = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
    next_cond_id = (res_cond.data[0]['id'] + 1) if res_cond.data else 1

    cond1 = {
        "id": next_cond_id,
        "name": "CLOSE > EMA9 15M",
        "variable_id": close_var_id,
        "operator": ">",
        "value_type": "variable",
        "value_variable": ema9_var_id,
        "description": "El precio cierra encima de la EMA9 en 15 minutos",
        "enabled": True
    }
    
    cond2 = {
        "id": next_cond_id + 1,
        "name": "CLOSE > EMA3 15M",
        "variable_id": close_var_id,
        "operator": ">",
        "value_type": "variable",
        "value_variable": ema3_var_id,
        "description": "El precio cierra encima de la EMA3 en 15 minutos",
        "enabled": True
    }

    sb.table('strategy_conditions').upsert(cond1).execute()
    sb.table('strategy_conditions').upsert(cond2).execute()
    
    print(f"Inserted condition: {cond1['name']} with ID {cond1['id']}")
    print(f"Inserted condition: {cond2['name']} with ID {cond2['id']}")

if __name__ == "__main__":
    asyncio.run(add_close_conditions())
