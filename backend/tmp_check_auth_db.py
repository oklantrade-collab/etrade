import os
import sys
from app.core.supabase_client import get_supabase

def check_tables():
    sb = get_supabase()
    try:
        res = sb.table('roles').select('nombre, codigo_registro').execute()
        print(f"✅ Found {len(res.data)} roles in DB.")
        for r in res.data:
            print(f"   - {r['nombre']}: {r['codigo_registro']}")
    except Exception as e:
        print(f"❌ Roles table error: {e}")

    try:
        res = sb.table('usuarios').select('id', count='exact').execute()
        print(f"✅ Usuarios table exists. Count: {res.count}")
    except Exception as e:
        print(f"❌ Usuarios table error: {e}")

if __name__ == "__main__":
    check_tables()
