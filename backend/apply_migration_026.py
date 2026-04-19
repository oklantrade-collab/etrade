import os
import sys
from dotenv import load_dotenv

# Asegurar que el path incluya el directorio actual
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def apply_migration():
    load_dotenv('c:/Fuentes/eTrade/backend/.env')

    from app.core.supabase_client import get_supabase
    sb = get_supabase()
    
    sql_path = 'c:/Fuentes/eTrade/backend/migration_026_smart_limit.sql'
    if not os.path.exists(sql_path):
        print(f"Error: {sql_path} no existe.")
        return

    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()
        
    print(f"Aplicando migración desde {sql_path} vía RPC...")
    
    # Dividir por punto y coma para ejecutar segmentos
    queries = [q.strip() for q in sql.split(';') if q.strip()]
    
    for i, query in enumerate(queries):
        try:
            full_query = query + ";"
            sb.rpc('exec_sql', {'sql_query': full_query}).execute()
            print(f"  OK: Query {i+1} ejecutada.")
        except Exception as e:
            print(f"  ERR: Query {i+1} falló: {e}")

    print("MIGRACIÓN 026 COMPLETADA ✅")

if __name__ == "__main__":
    apply_migration()
