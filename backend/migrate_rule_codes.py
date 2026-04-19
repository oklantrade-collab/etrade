import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

mapping = {
    'PRO_BUY_MKT': 'S01', 'PRO_BUY_LMT': 'S02', 
    'PRO_SELL_MKT': 'S03', 'PRO_SELL_LMT': 'S04',
    'HOT_BUY_MKT': 'S05', 'HOT_BUY_LMT': 'S06',
    'HOT_SELL_MKT': 'S07', 'HOT_SELL_LMT': 'S08'
}

def migrate():
    # 1. Get current rules
    res = sb.table('stocks_rules').select('*').execute()
    rules = res.data or []
    
    # 2. Insert temporary copies
    for r in rules:
        old_code = r['rule_code']
        if old_code not in mapping: continue
        temp_code = 'TEMP_' + old_code
        new_r = {**r}
        del new_r['id']
        new_r['rule_code'] = temp_code
        sb.table('stocks_rules').insert(new_r).execute()
        print(f"Created temp rule: {temp_code}")

    # 3. Update orders to temp
    for old_code in mapping:
        temp_code = 'TEMP_' + old_code
        sb.table('stocks_orders').update({'rule_code': temp_code}).eq('rule_code', old_code).execute()
        print(f"Updated orders for {old_code} to {temp_code}")

    # 4. Delete old rules
    for old_code in mapping:
        sb.table('stocks_rules').delete().eq('rule_code', old_code).execute()
        print(f"Deleted old rule: {old_code}")

    # 5. Rename temp rules to short codes
    for old_code, short_code in mapping.items():
        temp_code = 'TEMP_' + old_code
        # Insert actual short code rule
        res = sb.table('stocks_rules').select('*').eq('rule_code', temp_code).execute()
        if res.data:
            r = res.data[0]
            new_r = {**r}
            del new_r['id']
            new_r['rule_code'] = short_code
            sb.table('stocks_rules').insert(new_r).execute()
            
            # Update orders to short code
            sb.table('stocks_orders').update({'rule_code': short_code}).eq('rule_code', temp_code).execute()
            
            # Delete temp rule
            sb.table('stocks_rules').delete().eq('rule_code', temp_code).execute()
            print(f"Renamed {temp_code} to {short_code}")

if __name__ == "__main__":
    migrate()
