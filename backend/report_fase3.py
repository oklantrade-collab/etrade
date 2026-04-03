
import asyncio, os
from dotenv import load_dotenv
from supabase import create_client
from tabulate import tabulate

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

async def main():
    print("--- VERIFICACIÓN FINAL Fase 3 ---")
    
    # 1. Ver near-misses
    print("\n1. Near-misses (core >= 0.40):")
    res1 = sb.table('strategy_evaluations').select('symbol, rule_code, direction, score, triggered, conditions, created_at').gte('score', 0.40).order('score', desc=True).limit(10).execute()
    if res1.data:
        # Simplify conditions for display
        for row in res1.data:
            conds = row['conditions']
            row['conditions'] = ",".join([f"{k}:{v['passed']}" for k, v in conds.items()])[:30] + "..."
        print(tabulate(res1.data, headers="keys"))
    
    # 2. Ver evaluaciones por regla
    # (Since I can't do complex SQL GROUP BY via the client easily without RPC, I'll do it in Python)
    print("\n2. Evaluaciones por regla:")
    res2 = sb.table('strategy_evaluations').select('rule_code, direction, score, triggered').execute()
    if res2.data:
        summary = {}
        for row in res2.data:
            key = (row['rule_code'], row['direction'])
            if key not in summary:
                summary[key] = {'evaluaciones': 0, 'activaciones': 0, 'total_score': 0}
            summary[key]['evaluaciones'] += 1
            if row['triggered']:
                summary[key]['activaciones'] += 1
            summary[key]['total_score'] += row['score']
        
        table_data = []
        for (rc, dr), stats in summary.items():
            table_data.append({
                'rule_code': rc,
                'direction': dr,
                'evaluaciones': stats['evaluaciones'],
                'activaciones': stats['activaciones'],
                'score_promedio': round(stats['total_score'] / stats['evaluaciones'], 3)
            })
        table_data.sort(key=lambda x: x['activaciones'], reverse=True)
        print(tabulate(table_data, headers="keys"))

asyncio.run(main())
