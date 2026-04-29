"""
SLVM Database Migration — Uses Supabase REST SQL endpoint.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

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

# Build full SQL
sql_statements = []
for table in TABLES:
    for col_name, col_type in SLVM_COLUMNS:
        sql_statements.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type};")

full_sql = "\n".join(sql_statements)

# Execute via Supabase SQL endpoint (pg REST)
# The /rest/v1/rpc endpoint doesn't work, but we can use the SQL API
# Try the direct Supabase PostgreSQL connection string
# Format: postgresql://postgres.[ref]:[password]@[host]:5432/postgres

# Extract ref from URL
import re
ref_match = re.search(r'https://(\w+)\.supabase\.co', SUPABASE_URL)
ref = ref_match.group(1) if ref_match else None

if ref:
    print(f"Supabase project ref: {ref}")
    print(f"\nPlease run the following SQL in Supabase SQL Editor:")
    print(f"URL: {SUPABASE_URL.replace('.co', '.co/project/' + ref + '/sql/new')}")
    print(f"\n{'='*60}")
    print(full_sql)
    print(f"{'='*60}")
    
    # Also try to verify via REST API
    print("\n\nVerifying existing columns via REST API...")
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    for table in TABLES:
        try:
            res = sb.table(table).select("slv_price").limit(1).execute()
            print(f"  {table}: slv_price already exists!")
        except:
            print(f"  {table}: slv_price NOT found - migration needed")
    
    # Write SQL to file for convenience
    sql_file = os.path.join(os.path.dirname(__file__), 'slvm_migration.sql')
    with open(sql_file, 'w') as f:
        f.write("-- SLVM Migration: Stop Loss Virtual con Modo Recuperacion\n")
        f.write("-- Run this in Supabase SQL Editor\n\n")
        f.write(full_sql)
        f.write("\n\n-- Verify:\n")
        for table in TABLES:
            f.write(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' AND (column_name LIKE '%slv%' OR column_name LIKE '%recovery%') ORDER BY column_name;\n")
    print(f"\nSQL file saved to: {sql_file}")
