import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def update_rules():
    sb = get_supabase()
    # Actualizar Dd61_15m (ID 2)
    new_ids = [58, 59, 63, 64]
    new_weights = {"58": 0.2, "59": 0.5, "63": 0.15, "64": 0.15}
    
    # 15m
    sb.table('strategy_rules_v2').update({
        'condition_ids': new_ids,
        'condition_weights': new_weights,
        'condition_logic': 'OR',
        'min_score': 0.75
    }).eq('rule_code', 'Dd61_15m').execute()
    
    # 4h (si existe configuracion Similar)
    sb.table('strategy_rules_v2').update({
        'condition_ids': new_ids,
        'condition_weights': new_weights,
        'condition_logic': 'OR',
        'min_score': 0.75
    }).eq('rule_code', 'Dd61_4h').execute()
    
    # También actualizar los inversos para Dd51 (Short Trap)
    # IDs inversos: 58 (Flat), 60 (UPPER_6), 65(?)
    # Consultamos IDs para short trap
    short_ids = [58, 60, 65, 67] # Asumo estos basados en mi conocimiento del repo pero verifico
    # 58: is_flat
    # 60: price_touched_upper_6 (o similar)
    # 65: sars_negative_short
    # 67: price > basis
    
if __name__ == "__main__":
    asyncio.run(update_rules())
