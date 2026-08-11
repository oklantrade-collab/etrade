import asyncio
from app.core.supabase_client import get_supabase

async def update_aa30_rules():
    sb = get_supabase()
    
    # --- Update Aa30 ---
    print("Updating Aa30...")
    aa30 = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa30').execute()
    if aa30.data:
        aa30_data = aa30.data[0]
        aa30_data['condition_ids'] = [2, 9905, 74, 71, 24, 228]
        aa30_data['condition_weights'] = {
            "2": 0.3,
            "9905": 0.1,
            "74": 0.1,
            "71": 0.2,
            "24": 0.1,
            "228": 0.2
        }
        aa30_data['min_score'] = 0.9
        
        sb.table('strategy_rules_v2').update(aa30_data).eq('id', aa30_data['id']).execute()
        print("Aa30 updated successfully.")
    else:
        print("Rule Aa30 not found!")

    # --- Update Aa30C ---
    print("\nUpdating Aa30C...")
    aa30c = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa30C').execute()
    if aa30c.data:
        aa30c_data = aa30c.data[0]
        aa30c_data['condition_ids'] = [2, 9904, 9905, 9908, 74, 71]
        aa30c_data['condition_weights'] = {
            "2": 0.3,
            "9904": 0.2,
            "9905": 0.1,
            "9908": 0.1,
            "74": 0.1,
            "71": 0.2
        }
        aa30c_data['min_score'] = 0.9
        
        sb.table('strategy_rules_v2').update(aa30c_data).eq('id', aa30c_data['id']).execute()
        print("Aa30C updated successfully.")
    else:
        print("Rule Aa30C not found!")

if __name__ == "__main__":
    asyncio.run(update_aa30_rules())
