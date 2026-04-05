import asyncio
import httpx
from app.core.supabase_client import get_supabase

async def update_aa_rules():
    sb = get_supabase()
    
    print("Updating Aa11...")
    # Fetch current Aa11 to preserve existing data structure if any (though we know the exact IDs)
    res11 = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa11').execute()
    if res11.data:
        rule = res11.data[0]
        # Current IDs: [26, 40, 36, 54]
        # Current weights: {'26': 0.2, '36': 0.25, '40': 0.15, '54': 0.4}
        new_ids = [26, 40, 36, 54, 201]
        new_weights = {'26': 0.2, '36': 0.25, '40': 0.15, '54': 0.3, '201': 0.1}
        
        sb.table('strategy_rules_v2').update({
            'condition_ids': new_ids,
            'condition_weights': new_weights
        }).eq('rule_code', 'Aa11').execute()
        print("Updated Aa11")
    else:
        print("Aa11 not found")

    print("\nUpdating Aa12...")
    res12 = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa12').execute()
    if res12.data:
        rule = res12.data[0]
        # Current IDs: [69, 70, 71, 72]
        # Current weights: {'69': 0.4, '70': 0.2, '71': 0.2, '72': 0.2}
        new_ids = [69, 70, 71, 72, 201]
        new_weights = {'69': 0.3, '70': 0.2, '71': 0.2, '72': 0.2, '201': 0.1}
        
        sb.table('strategy_rules_v2').update({
            'condition_ids': new_ids,
            'condition_weights': new_weights
        }).eq('rule_code', 'Aa12').execute()
        print("Updated Aa12")
    else:
        print("Aa12 not found")
        
    print("\nReloading strategy engine...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get('http://localhost:8080/api/v1/strategies/reload')
            print(f"Reload response: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Failed to reload engine: {e}")

if __name__ == "__main__":
    asyncio.run(update_aa_rules())
