import os
from dotenv import load_dotenv
from supabase import create_client
import sys

# Path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.parameter_guard import get_active_params

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("Current Thresholds:")
for regime in ['bajo_riesgo', 'riesgo_medio', 'alto_riesgo']:
    params = get_active_params(regime, sb)
    print(f"  {regime:15}: mtf={params.get('mtf_threshold')} | rr_min={params.get('rr_min')}")
