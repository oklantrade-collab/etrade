import asyncio
import os
import sys
from app.core.supabase_client import get_supabase

# Añadir el path base para importar app
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def check_open_positions():
    sb = get_supabase()
    # Check open positions
    open_p = sb.table('positions').select('*').eq('status', 'open').execute()
    if open_p.data:
        print("--- OPEN POSITIONS ---")
        for p in open_p.data:
            print(f"Data: {p}")
    else:
        print("No open positions found in 'positions' table.")

if __name__ == "__main__":
    asyncio.run(check_open_positions())
