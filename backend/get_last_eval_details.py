import asyncio
import os
import sys
import json
from app.core.supabase_client import get_supabase

# Añadir el path base para importar app
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def get_last_eval():
    sb = get_supabase()
    
    print("--- Buscando las últimas 20 evaluaciones en strategy_evaluations ---")
    res = sb.table('strategy_evaluations').select('*').order('created_at', desc=True).limit(20).execute()
    
    if not res.data:
        print("No se encontraron evaluaciones.")
        return

    for ev in res.data:
        print(f"\n{ev['created_at']} | {ev['symbol']} | Rule: {ev['rule_code']} | Score: {ev['score']} | Triggered: {ev['triggered']}")

if __name__ == "__main__":
    asyncio.run(get_last_eval())
