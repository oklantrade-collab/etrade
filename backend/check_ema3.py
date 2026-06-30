import sys
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check_ema3_variables():
    sb = get_supabase()
    res = sb.table('strategy_variables').select('*').ilike('name', '%EMA3%').execute()
    for var in res.data:
        print(f"ID: {var['id']}, Name: {var['name']}, Source: {var['source_field']}, Category: {var['category']}")
        
    print("---")
    res2 = sb.table('strategy_conditions').select('*').ilike('name', '%EMA3%').execute()
    for cond in res2.data:
         print(f"Cond ID: {cond['id']}, Name: {cond['name']}, Var ID: {cond['variable_id']}")

if __name__ == "__main__":
    check_ema3_variables()
