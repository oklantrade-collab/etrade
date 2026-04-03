from app.core.supabase_client import get_supabase
import sys

def add_column():
    sb = get_supabase()
    print("Intentando agregar columna direction_evaluated a pilot_diagnostics...")
    
    # Intento de RPC genérico o PostgREST directo (probablemente falle si no hay RPC)
    try:
        # En Supabase no hay raw SQL por defecto vía API
        # Probamos insertando una fila con esa columna para forzar esquema (no funciona)
        # Probamos llamando a un RPC de mantenimiento si existe
        res = sb.rpc('exec_sql', {'sql': 'ALTER TABLE pilot_diagnostics ADD COLUMN direction_evaluated TEXT;'}).execute()
        print("Éxito vía RPC exec_sql")
    except Exception as e:
        print(f"RPC exec_sql falló o no existe: {e}")
        print("No se puede añadir columnas dinámicamente sin acceso SQL directo.")
        print("Suponiendo que el usuario lo hará o consultaremos las columnas existentes.")

if __name__ == "__main__":
    add_column()
