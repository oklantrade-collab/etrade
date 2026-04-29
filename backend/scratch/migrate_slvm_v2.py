"""
SLVM Database Migration — Add columns for Stop Loss Virtual con Modo Recuperacion.
Uses psycopg2 for direct ALTER TABLE commands on Supabase Postgres.
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')

TABLES = ["positions", "forex_positions", "stocks_positions"]

SLVM_COLUMNS = [
    ("slv_price",                "NUMERIC"),
    ("slv_triggered",            "BOOLEAN DEFAULT false"),
    ("slv_triggered_at",         "TIMESTAMPTZ"),
    ("slv_triggered_price",      "NUMERIC"),
    ("recovery_mode",            "BOOLEAN DEFAULT false"),
    ("recovery_cycles",          "INTEGER DEFAULT 0"),
    ("recovery_max_cycles",      "INTEGER DEFAULT 12"),
    ("recovery_target_price",    "NUMERIC"),
    ("recovery_exit_price",      "NUMERIC"),
    ("recovery_exit_reason",     "VARCHAR(50)"),
    ("lowest_price_in_recovery", "NUMERIC"),
    ("recovery_pnl_pips",        "NUMERIC"),
]

db_url = os.getenv('DATABASE_URL')
if not db_url:
    print("ERROR: DATABASE_URL not set in .env")
    exit(1)

conn = psycopg2.connect(db_url)
cur = conn.cursor()

for table in TABLES:
    print(f"\n--- Migrating: {table} ---")
    for col_name, col_type in SLVM_COLUMNS:
        sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
        try:
            cur.execute(sql)
            print(f"  + {col_name} ({col_type})")
        except Exception as e:
            print(f"  ! {col_name}: {e}")
            conn.rollback()

conn.commit()

# Verify
print("\n--- VERIFICATION ---")
for table in TABLES:
    cur.execute(f"""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = '{table}' 
        AND (column_name LIKE '%slv%' OR column_name LIKE '%recovery%')
        ORDER BY column_name;
    """)
    cols = [r[0] for r in cur.fetchall()]
    status = "OK" if len(cols) >= 12 else "INCOMPLETE"
    print(f"  {table}: {status} ({len(cols)} SLVM columns) -> {', '.join(cols)}")

cur.close()
conn.close()
print("\nMigration complete!")
