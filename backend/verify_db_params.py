import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
supabase = create_client(url, key)

def verify():
    res = supabase.table('parameter_bounds').select('parameter_name, current_value').in_('parameter_name', ['rr_min_bajo_riesgo', 'rr_min_riesgo_medio', 'rr_min_alto_riesgo']).execute()
    print("--- PARAMETER VALUES ---")
    for r in res.data:
        print(f"{r['parameter_name']}: {r['current_value']}")
        
    # Check if rr_min_riesgo_medio is 2.5
    for r in res.data:
        if r['parameter_name'] == 'rr_min_riesgo_medio' and r['current_value'] != 2.5:
             print("FIXING rr_min_riesgo_medio to 2.5...")
             supabase.table('parameter_bounds').update({'current_value': 2.5}).eq('parameter_name', 'rr_min_riesgo_medio').execute()
             print("FIXED.")

if __name__ == "__main__":
    verify()
