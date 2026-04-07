import asyncio
import os
import sys
from app.core.supabase_client import get_supabase

# Añadir el path base para importar app
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def list_all_rules():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('*').execute()
    print("--- TODAS LAS REGLAS ---")
    for r in res.data:
        print(f"Code: {r['rule_code']} | Name: {r['name']}")

if __name__ == "__main__":
    asyncio.run(list_all_rules())
