import asyncio
import os
import sys
import json
from app.core.supabase_client import get_supabase

# Añadir el path base para importar app
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def get_latest_high_score():
    sb = get_supabase()
    # Fetch rules to know min_scores
    rules = sb.table('strategy_rules_v2').select('rule_code, min_score, name').execute().data
    rule_map = {r['rule_code']: r for r in rules}
    
    print("--- Buscando evaluaciones recientes con puntuación alta ---")
    res = sb.table('strategy_evaluations').select('*').order('created_at', desc=True).limit(50).execute()
    
    found = False
    for ev in res.data:
        rule_code = ev['rule_code']
        min_score = float(rule_map.get(rule_code, {}).get('min_score', 0.6))
        score = float(ev.get('score', 0))
        
        if score >= min_score or ev.get('triggered'):
            print(f"\n--- ENCONTRADA: {ev['created_at']} | {ev['symbol']} | {rule_code} ---")
            print(f"Nombre Regla: {rule_map.get(rule_code, {}).get('name')}")
            print(f"Score: {score} (Min: {min_score}) | Triggered: {ev['triggered']}")
            print(f"Valores Contexto: {json.dumps(ev.get('context', {}))}")
            print(f"Condiciones: {json.dumps(ev.get('conditions', {}))}")
            found = True
            break # Just take the most recent one
            
    if not found:
        print("No se encontraron evaluaciones recientes que cumplieran el marcador.")

if __name__ == "__main__":
    asyncio.run(get_latest_high_score())
