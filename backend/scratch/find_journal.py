import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def find_journal():
    sb = get_supabase()
    # Check common journal table names
    tables = ['journal', 'forex_journal', 'trades_journal', 'performance_metrics', 'trades_active', 'trades_history']
    for t in tables:
        try:
            res = sb.table(t).select('id').limit(1).execute()
            print(f"Table '{t}' exists.")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(find_journal())
