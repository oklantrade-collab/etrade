import asyncio
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    res_evals = sb.table('strategy_evaluations').select('*').order('created_at', desc=True).limit(20).execute()
    print("--- ULTIMAS EVALUACIONES ---")
    for row in res_evals.data:
        print(f"[{row['symbol']}] Regla: {row['rule_code']} | Score: {row['score']:.2f} | Activo: {row['triggered']}")
        if 'conditions' in row and row['conditions']:
            failed = []
            for k, v in row['conditions'].items():
                if not v.get('passed'):
                    failed.append(v.get('name'))
            if failed:
                print(f"  -> Fallaron ({len(failed)}): {', '.join(failed)}")

asyncio.run(check())
