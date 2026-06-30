import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

def update_aa30_db():
    print("--- Updating Rule Aa30 ---")
    rule_id_query = sb.table('strategy_rules_v2').select('id').eq('rule_code', 'Aa30').execute()
    if not rule_id_query.data:
        print("Rule Aa30 not found!")
        return
    rule_id = rule_id_query.data[0]['id']
    
    # Existing IDs from previous analysis:
    # 9904: EMA3 > EMA9 5m
    # 9905: EMA9 > EMA20 5m
    # 9908: EMA20 ángulo positivo 5m
    # We are adding ID 2: EMA9 > EMA20 (15m) (Aa12)
    
    condition_ids = [2, 9904, 9905, 9908]
    
    rule_data = {
        "notes": "Estrategia alcista (5m): 15m EMA9>EMA20 (40%), 5m EMA3>EMA9 (20%), 5m EMA9>EMA20 (20%), 5m EMA20_angle_pos (20%).",
        "condition_ids": condition_ids,
        "condition_weights": {
            "2": 0.40,
            "9904": 0.20,
            "9905": 0.20,
            "9908": 0.20
        },
        "applicable_cycles": ["15m", "5m"]
    }
    sb.table('strategy_rules_v2').update(rule_data).eq('id', rule_id).execute()
    print("Rule Aa30 updated.")

if __name__ == "__main__":
    update_aa30_db()
