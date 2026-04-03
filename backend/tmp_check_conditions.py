from app.core.supabase_client import get_supabase
import asyncio
import json
import sys

# Set encoding to utf-8
sys.stdout.reconfigure(encoding='utf-8')

async def check_conditions():
    sb = get_supabase()
    res = sb.table('strategy_conditions').select('*, variable:strategy_variables(*)').execute()
    for c in res.data:
        v = c.get('variable') or {}
        print(f"ID: {c['id']}, Name: {c['name']}, Operator: {c['operator']}, Value: {c.get('value_literal') or c.get('value_list')}, Source: {v.get('source_field')}")

if __name__ == "__main__":
    asyncio.run(check_conditions())
