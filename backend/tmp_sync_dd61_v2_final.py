import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def update_rules():
    sb = get_supabase()
    
    # ── LONG TRAP (Dd61) ──
    long_ids = [58, 59, 63, 64]
    long_weights = {"58": 0.2, "59": 0.5, "63": 0.15, "64": 0.15}
    
    for rule in ['Dd61_15m', 'Dd61_4h']:
        sb.table('strategy_rules_v2').update({
            'condition_ids': long_ids,
            'condition_weights': long_weights,
            'condition_logic': 'OR',
            'min_score': 0.75
        }).eq('rule_code', rule).execute()
        print(f"Updated {rule}")

    # ── SHORT TRAP (Dd51) ──
    short_ids = [58, 60, 66, 68]
    short_weights = {"58": 0.2, "60": 0.5, "66": 0.15, "68": 0.15}
    
    # Verifico si existen Dd51_15m y Dd51_4h
    for rule in ['Dd51_15m', 'Dd51_4h']:
        sb.table('strategy_rules_v2').update({
            'condition_ids': short_ids,
            'condition_weights': short_weights,
            'condition_logic': 'OR',
            'min_score': 0.75
        }).eq('rule_code', rule).execute()
        print(f"Updated {rule}")

if __name__ == "__main__":
    asyncio.run(update_rules())
