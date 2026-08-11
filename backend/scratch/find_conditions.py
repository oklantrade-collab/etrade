import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

def find_conditions():
    sb = get_supabase()
    
    print("--- Searching for RSI conditions ---")
    res_rsi = sb.table('strategy_conditions').select('id,name,description,indicator,operator,value').ilike('indicator', '%RSI%').execute()
    for c in res_rsi.data:
        print(c)
        
    print("\n--- Searching for ADX conditions ---")
    res_adx = sb.table('strategy_conditions').select('id,name,description,indicator,operator,value').ilike('indicator', '%ADX%').execute()
    for c in res_adx.data:
        print(c)

if __name__ == '__main__':
    find_conditions()
