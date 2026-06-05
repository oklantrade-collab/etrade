import os
import sys
# Add backend to PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

from app.core.supabase_client import get_supabase

def print_columns():
    sb = get_supabase()
    res = sb.table('positions').select('*').limit(1).execute()
    if res.data:
        print("POSITIONS columns:")
        print(sorted(list(res.data[0].keys())))
    else:
        print("No crypto positions found")
        
    res2 = sb.table('forex_positions').select('*').limit(1).execute()
    if res2.data:
        print("\nFOREX POSITIONS columns:")
        print(sorted(list(res2.data[0].keys())))
    else:
        print("No forex positions found")

if __name__ == "__main__":
    print_columns()
