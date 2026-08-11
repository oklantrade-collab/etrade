import asyncio
from app.core.supabase_client import get_supabase

async def update_strategies():
    sb = get_supabase()
    
    # IDs de las nuevas condiciones
    cond_close_ema9 = 9918
    cond_close_ema3 = 9919
    
    # Obtener estrategias Bb23 y Bb13
    res = sb.table('strategy_rules_v2').select('*').in_('rule_code', ['Bb23', 'Bb13']).execute()
    
    if not res.data:
        print("No se encontraron las estrategias Bb23 o Bb13.")
        return
        
    for rule in res.data:
        rule_code = rule['rule_code']
        cond_ids = rule.get('condition_ids', [])
        
        # Añadir si no están
        added = False
        if cond_close_ema9 not in cond_ids:
            cond_ids.append(cond_close_ema9)
            added = True
        if cond_close_ema3 not in cond_ids:
            cond_ids.append(cond_close_ema3)
            added = True
            
        if added:
            print(f"Actualizando {rule_code} con nuevas condiciones: {cond_ids}")
            sb.table('strategy_rules_v2').update({'condition_ids': cond_ids}).eq('id', rule['id']).execute()
        else:
            print(f"Estrategia {rule_code} ya tiene las condiciones actualizadas.")

if __name__ == "__main__":
    asyncio.run(update_strategies())
