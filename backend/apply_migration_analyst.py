from app.core.supabase_client import get_supabase

def apply_analyst_migration():
    sb = get_supabase()
    print("Aplicando migracion para columna 'analyst_rating'...")
    
    sql = "ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS analyst_rating FLOAT DEFAULT 0;"
    
    try:
        sb.rpc('exec_sql', {'sql_query': sql}).execute()
        print("✅ Columna 'analyst_rating' añadida con éxito.")
    except Exception as e:
        print(f"❌ Error al aplicar SQL: {e}")
        print("Es posible que necesites añadir la columna manualmente en el Dashboard de Supabase.")

if __name__ == "__main__":
    apply_analyst_migration()
