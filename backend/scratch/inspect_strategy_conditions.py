import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def inspect_conds():
    sb = get_supabase()
    res = sb.table('strategy_conditions').select('id, name, description').order('id').execute()
    print("=== STRATEGY CONDITIONS EN SUPABASE ===")
    for c in res.data or []:
        print(f"ID {c['id']}: {c['name']} | Desc: {c.get('description')}")

if __name__ == "__main__":
    inspect_conds()
