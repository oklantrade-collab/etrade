import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

TABLES = ["positions", "forex_positions", "stocks_positions"]
SLVM_COLS = ["slv_price", "recovery_mode", "recovery_cycles", "slv_triggered",
             "slv_triggered_at", "slv_triggered_price", "recovery_max_cycles",
             "recovery_target_price", "recovery_exit_price", "recovery_exit_reason",
             "lowest_price_in_recovery", "recovery_pnl_pips"]

async def check():
    sb = get_supabase()
    for table in TABLES:
        print(f"\n--- {table} ---")
        try:
            cols = ", ".join(SLVM_COLS)
            res = sb.table(table).select(cols).limit(1).execute()
            print(f"  ALL SLVM columns already exist!")
        except Exception as e:
            err = str(e)
            print(f"  Missing columns detected: {err[:100]}")
            # Try each individually
            for col in SLVM_COLS:
                try:
                    sb.table(table).select(col).limit(1).execute()
                    print(f"    OK: {col}")
                except:
                    print(f"    MISSING: {col}")

if __name__ == "__main__":
    asyncio.run(check())
