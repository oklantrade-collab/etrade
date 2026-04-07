import asyncio
import os
import sys
from app.core.supabase_client import get_supabase

# Añadir el path base para importar app
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def check_signals():
    sb = get_supabase()
    res = sb.table('signals').select('*').order('created_at', desc=True).limit(5).execute()
    print("--- ULTIMAS SEÑALES ---")
    for s in res.data:
        print(f"Time: {s['created_at']} | Symbol: {s['symbol']} | Side: {s['side']} | Strategy: {s.get('strategy_id') or s.get('rule_code')}")

if __name__ == "__main__":
    asyncio.run(check_signals())
