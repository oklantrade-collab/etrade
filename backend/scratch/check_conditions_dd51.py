import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_conditions():
    sb = get_supabase()
    ids = [58, 60, 202, 204, 27, 35]
    try:
        res = sb.table("strategy_conditions").select("id, name, operator, value_literal, variable:strategy_variables(*)").in_("id", ids).execute()
        for c in res.data:
            v = c.get('variable') or {}
            print(f"ID {c['id']}: {c['name']} | Var: {v.get('name')} | Op: {c['operator']} | Val: {c['value_literal']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_conditions())
