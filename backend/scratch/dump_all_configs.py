import asyncio
import os
import sys
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.supabase_client import get_supabase

async def dump():
    sb = get_supabase()
    tables = ["trading_config", "risk_config", "bot_config", "system_config"]
    results = {}
    for table in tables:
        try:
            res = sb.table(table).select("*").execute()
            results[table] = res.data
        except Exception as e:
            results[table] = f"Error: {e}"
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(dump())
