
import asyncio, os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

async def main():
    print("--- VERIFICACIÓN FINAL Fase 3 ---")
    
    # 1. Ver near-misses
    print("\n1. Near-misses (score >= 0.40):")
    res1 = sb.table('strategy_evaluations').select('symbol, rule_code, direction, score, triggered, created_at').gte('score', 0.40).order('score', desc=True).limit(10).execute()
    if res1.data:
        print(f"{'SYMBOL':<10} | {'RULE':<8} | {'DIR':<6} | {'SCORE':<6} | {'TRIG':<6} | {'DATE'}")
        print("-" * 70)
        for row in res1.data:
            print(f"{row['symbol']:<10} | {row['rule_code']:<8} | {row['direction']:<6} | {row['score']:<6.2f} | {row['triggered']:<6} | {row['created_at']}")
    
    # 2. Ver evaluaciones por regla
    print("\n2. Evaluaciones por regla:")
    res2 = sb.table('strategy_evaluations').select('rule_code, direction, score, triggered').execute()
    if res2.data:
        summary = {}
        for row in res2.data:
            key = (row['rule_code'], row['direction'])
            if key not in summary:
                summary[key] = {'evaluaciones': 0, 'activaciones': 0, 'total_score': 0}
            summary[key]['evaluaciones'] += 1
            if row['triggered']: summary[key]['activaciones'] += 1
            summary[key]['total_score'] += row['score']
        
        table_data = []
        for (rc, dr), stats in summary.items():
            table_data.append({
                'rule_code': rc, 'direction': dr, 
                'evaluaciones': stats['evaluaciones'], 'activaciones': stats['activaciones'],
                'score_avg': round(stats['total_score'] / stats['evaluaciones'], 3)
            })
        table_data.sort(key=lambda x: x['activaciones'], reverse=True)
        
        print(f"{'RULE':<8} | {'DIR':<6} | {'EVALS':<6} | {'TRIGS':<6} | {'AVG_SCORE'}")
        print("-" * 50)
        for row in table_data:
            print(f"{row['rule_code']:<8} | {row['direction']:<6} | {row['evaluaciones']:<6} | {row['activaciones']:<6} | {row['score_avg']:<10.3f}")

asyncio.run(main())
