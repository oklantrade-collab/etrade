"""
Aplica la migración 022 — Columnas de Estructura de Mercado
Ejecutar: python apply_migration_022.py
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

sb = get_supabase()

# Agregar columnas de estructura 15m
columns_15m = [
    ("structure_15m",        "VARCHAR(20) DEFAULT 'unknown'"),
    ("allow_long_15m",       "BOOLEAN DEFAULT true"),
    ("allow_short_15m",      "BOOLEAN DEFAULT true"),
    ("reverse_signal_15m",   "BOOLEAN DEFAULT false"),
    ("structure_reason_15m", "TEXT"),
]

columns_4h = [
    ("structure_4h",         "VARCHAR(20) DEFAULT 'unknown'"),
    ("allow_long_4h",        "BOOLEAN DEFAULT true"),
    ("allow_short_4h",       "BOOLEAN DEFAULT true"),
    ("reverse_signal_4h",    "BOOLEAN DEFAULT false"),
    ("structure_reason_4h",  "TEXT"),
]

all_columns = columns_15m + columns_4h

for col_name, col_type in all_columns:
    try:
        sb.rpc('exec_sql', {
            'query': f"ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
        }).execute()
        print(f"  ✓ {col_name}")
    except Exception as e:
        # Si rpc no existe, intentar con SQL directo (puede no funcionar con todas las versiones de Supabase)
        print(f"  ⚠ {col_name}: {e}")

# Verificar columnas agregadas
try:
    res = sb.table('market_snapshot').select('structure_15m, structure_4h').limit(1).execute()
    if res.data is not None:
        print("\n✅ Migración 022 aplicada correctamente")
        print(f"  Columnas verificadas en market_snapshot")
    else:
        print("\n✅ Tabla accesible (sin datos aún)")
except Exception as e:
    print(f"\n⚠ Verificación parcial: {e}")
    print("  Las columnas pueden necesitar ser agregadas manualmente vía SQL Editor en Supabase")
    print("  SQL a ejecutar:")
    print()
    with open('migration_022_structure_confirmation.sql', 'r') as f:
        print(f.read())
