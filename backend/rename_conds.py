import sys
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def rename_ema3_conds():
    sb = get_supabase()
    # Rename 207
    sb.table('strategy_conditions').update({'name': 'EMA3 > EMA9 (TF Estrategia)'}).eq('id', 207).execute()
    # Rename 214
    sb.table('strategy_conditions').update({'name': 'EMA3 < EMA9 (TF Estrategia)'}).eq('id', 214).execute()
    print("Renamed condition 207 to 'EMA3 > EMA9 (TF Estrategia)'")
    print("Renamed condition 214 to 'EMA3 < EMA9 (TF Estrategia)'")

if __name__ == "__main__":
    rename_ema3_conds()
