import asyncio
import os
import sys
from app.core.supabase_client import get_supabase

# Añadir el path base para importar app
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def list_tables():
    sb = get_supabase()
    # In Supabase/PostgreSQL, we can query public schema tables
    res = sb.rpc('get_tables', {}).execute()
    # Wait, if RPC doesn't exist, we can try querying information_schema
    # But supabase-py doesn't allow direct SELECT from information_schema easily via .table()
    # Let's try some common table names
    test_tables = ['strategies', 'trading_rules', 'rules', 'conditions', 'rule_conditions', 'signals', 'paper_trades', 'orders']
    for t in test_tables:
        try:
            sb.table(t).select('count', count='exact').limit(1).execute()
            print(f"Table exists: {t}")
        except Exception as e:
            print(f"Table missing/error: {t}")

if __name__ == "__main__":
    asyncio.run(list_tables())
