import asyncio
from app.core.supabase_client import get_supabase

async def check_columns():
    sb = get_supabase()
    tables = ['paper_trades', 'forex_positions', 'stocks_positions']
    for table in tables:
        print(f"\n--- Table: {table} ---")
        try:
            res = sb.table(table).select('*').limit(1).execute()
            if res.data:
                print(f"Columns: {list(res.data[0].keys())}")
            else:
                print("No data to infer columns, trying select('*') with limit 0")
                # This might not work to get columns in all clients, but let's see
        except Exception as e:
            print(f"Error checking {table}: {e}")

if __name__ == "__main__":
    import os
    import sys
    sys.path.append(os.path.join(os.getcwd(), 'backend'))
    asyncio.run(check_columns())
