import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
supabase = create_client(url, key)

def verify_all():
    res = supabase.table('parameter_bounds').select('parameter_name, category, regime, current_value').execute()
    print("--- FULL PARAMETER LIST ---")
    for r in res.data:
        print(f"{r['parameter_name']} | {r['category']} | {r['regime']} | {r['current_value']}")

if __name__ == "__main__":
    verify_all()
