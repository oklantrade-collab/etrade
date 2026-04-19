from app.core.supabase_client import get_supabase

def add_analyst_column():
    sb = get_supabase()
    print("Intentando agregar columna 'analyst_rating' a 'watchlist_daily'...")
    
    # En Supabase, si no tenemos acceso a SQL directo, 
    # a veces podemos usar RPC o simplemente avisar al usuario.
    # Pero intentaré ver si hay una migración pendiente.
    
    # Sin embargo, como estoy como Agente, lo más seguro es crear un script 
    # que inserte un dato de prueba; si falla con "column does not exist", confirmamos.
    
    try:
        sb.table("watchlist_daily").update({"analyst_rating": 5}).eq("ticker", "AAPL").execute()
        print("✅ Columna detectada y actualizada.")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nDEBES EJECUTAR ESTO EN EL SQL EDITOR DE SUPABASE:")
        print("ALTER TABLE watchlist_daily ADD COLUMN analyst_rating FLOAT DEFAULT 0;")

if __name__ == "__main__":
    add_analyst_column()
