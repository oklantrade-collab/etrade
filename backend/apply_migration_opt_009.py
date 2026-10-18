"""
Aplica la migracion opt_009_catalyst_universe.sql a Supabase.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERROR] Faltan SUPABASE_URL o SUPABASE_SERVICE_KEY")
        return

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    sql_path = os.path.join(os.path.dirname(__file__), "sql", "opt_009_catalyst_universe.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    print("Aplicando migracion opt_009...")
    try:
        sb.rpc("exec_sql", {"sql_text": sql}).execute()
        print("[OK] Migracion opt_009 ejecutada con exito via RPC exec_sql")
    except Exception as e:
        print(f"[INFO] RPC exec_sql: {e}")

    # Verificar existencia de tablas
    for tbl in ["universe_pool", "universe_catalyst_events", "universe_catalyst_state", "opt_underlyings"]:
        try:
            res = sb.table(tbl).select("*").limit(1).execute()
            print(f"[OK] Tabla '{tbl}' accesible (filas leidas: {len(res.data or [])})")
        except Exception as err:
            print(f"[WARN] Tabla '{tbl}': {err}")

if __name__ == "__main__":
    main()
