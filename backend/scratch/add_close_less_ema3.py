import asyncio
from app.core.supabase_client import get_supabase

async def add_close_less_ema3():
    sb = get_supabase()
    
    # 1. Conseguir variable para 'close'
    res_var = sb.table('strategy_variables').select('id').eq('source_field', 'close').execute()
    if not res_var.data:
        print("Variable 'close' not found!")
        return
    close_var_id = res_var.data[0]['id']

    # 2. Conseguir ID de ema3
    res_ema3 = sb.table('strategy_variables').select('id').eq('source_field', 'ema3').execute()
    if not res_ema3.data:
        print("Variable 'ema3' not found!")
        return
    ema3_var_id = res_ema3.data[0]['id']

    # 3. Crear la condicion
    res_cond = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
    next_cond_id = (res_cond.data[0]['id'] + 1) if res_cond.data else 1

    cond = {
        "id": next_cond_id,
        "name": "CLOSE < EMA3 15M",
        "variable_id": close_var_id,
        "operator": "<",
        "value_type": "variable",
        "value_variable": ema3_var_id,
        "description": "El precio cierra debajo de la EMA3 en 15 minutos",
        "enabled": True
    }
    
    sb.table('strategy_conditions').upsert(cond).execute()
    print(f"Inserted condition: {cond['name']} with ID {cond['id']}")

if __name__ == "__main__":
    asyncio.run(add_close_less_ema3())
