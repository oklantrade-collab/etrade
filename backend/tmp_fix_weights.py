import asyncio
from app.core.supabase_client import get_supabase

async def fix_weights():
    sb = get_supabase()
    
    # 1. Update Dd61_15m and Dd61_4h weights (focus on 0.5 basis)
    # IDs: 58 (is_flat/Basis), 59 (LOWER_6), 63 (SAR 15m), 64 (Price < Basis)
    weights_61 = {'58': 0.50, '59': 0.30, '63': 0.10, '64': 0.10}
    
    for r_code in ['Dd61_15m', 'Dd61_4h']:
        sb.table('strategy_rules_v2').update({'condition_weights': weights_61}).eq('rule_code', r_code).execute()
        print(f"Updated {r_code} weights: {weights_61}")

    # 2. Update Dd51_15m and Dd51_4h weights
    # IDs: 58 (Basis), 60 (UPPER_6), 66 (SAR 15m), 68 (Price > Basis)
    weights_51 = {'58': 0.50, '60': 0.30, '66': 0.10, '68': 0.10}
    
    for r_code in ['Dd51_15m', 'Dd51_4h']:
        sb.table('strategy_rules_v2').update({'condition_weights': weights_51}).eq('rule_code', r_code).execute()
        print(f"Updated {r_code} weights: {weights_51}")

if __name__ == "__main__":
    asyncio.run(fix_weights())
