"""
SLVM Database Migration — Add columns for Stop Loss Virtual con Modo Recuperación.
Run this once to add the required columns to all 3 position tables.
"""
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

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

TABLES = ["positions", "forex_positions", "stocks_positions"]


async def run_migration():
    sb = get_supabase()
    
    for table in TABLES:
        print(f"\n{'='*50}")
        print(f"Migrating table: {table}")
        print(f"{'='*50}")
        
        for col_name, col_type in SLVM_COLUMNS:
            sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
            try:
                sb.rpc("exec_sql", {"query": sql}).execute()
                print(f"  ✅ {col_name} ({col_type})")
            except Exception as e:
                err = str(e)
                if "already exists" in err.lower() or "42701" in err:
                    print(f"  ⏭️  {col_name} (already exists)")
                else:
                    print(f"  ⚠️  {col_name}: {err}")
                    # Try direct approach
                    try:
                        # Alternative: just try to update with default values to verify column exists
                        test_res = sb.table(table).select(col_name).limit(1).execute()
                        print(f"     → Column verified via SELECT (OK)")
                    except Exception as e2:
                        print(f"     → Column needs manual creation: {col_name} {col_type}")

    # Verify
    print(f"\n{'='*50}")
    print("VERIFICATION")
    print(f"{'='*50}")
    
    for table in TABLES:
        try:
            res = sb.table(table).select("slv_price, recovery_mode, recovery_cycles").limit(1).execute()
            print(f"✅ {table}: SLVM columns accessible")
        except Exception as e:
            print(f"❌ {table}: {e}")
            print(f"   → Please add columns manually via Supabase SQL Editor:")
            for col_name, col_type in SLVM_COLUMNS:
                print(f"      ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type};")


if __name__ == "__main__":
    asyncio.run(run_migration())
