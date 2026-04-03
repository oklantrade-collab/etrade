import os
import asyncio
import json
from app.core.supabase_client import get_supabase

async def check_strategy_config():
    sb = get_supabase()
    
    # Check variables
    vars_res = sb.table('strategy_variables').select('*').execute()
    print("--- VARIABLES ---")
    for v in vars_res.data:
        print(f"ID: {v['id']} | Name: {v['name']} | Field: {v['source_field']}")
        
    # Check conditions
    conds_res = sb.table('strategy_conditions').select('*').execute()
    print("\n--- CONDITIONS ---")
    for c in conds_res.data:
        print(f"ID: {c['id']} | Name: {c['name']} | Op: {c['operator']} | Val: {c.get('value_literal') or c.get('value_variable')}")

if __name__ == "__main__":
    asyncio.run(check_strategy_config())
