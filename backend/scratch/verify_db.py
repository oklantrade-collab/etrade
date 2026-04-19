import os
import psycopg2
from dotenv import load_dotenv

def verify():
    # Cargar .env con ruta absoluta para evitar fallos de contexto
    load_dotenv(r'c:\Fuentes\eTrade\backend\.env')
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL no encontrada.")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Columnas a verificar
        cols = ['sl_type', 'sl_backstop_price', 'sl_dynamic_price', 'trailing_sl_price']
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'positions'")
        existing_cols = [row[0] for row in cur.fetchall()]
        
        found = [c for c in cols if c in existing_cols]
        print(f"Columnas detectadas en positions: {found}")
        
        # Verificar stocks_positions
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'stocks_positions'")
        existing_stocks_cols = [row[0] for row in cur.fetchall()]
        found_stocks = [c for c in cols if c in existing_stocks_cols]
        print(f"Columnas detectadas en stocks_positions: {found_stocks}")
        
        # Tabla sl_orders
        cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'sl_orders'")
        table_exists = cur.fetchone()[0] > 0
        print(f"Tabla sl_orders: {'EXISTE' if table_exists else 'NO ENCONTRADA'}")
        
        if len(found) == len(cols) and len(found_stocks) == len(cols) and table_exists:
            print("\n✅ CONFORMIDAD: Todo el ecosistema (Cripto/Forex/Stocks) está listo.")
        else:
            print("\n⚠ AVISO: Faltan algunos campos.")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    verify()
