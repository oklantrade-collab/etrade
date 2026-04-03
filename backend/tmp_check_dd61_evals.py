import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def check_evals():
    sb = get_supabase()
    evals = sb.table('strategy_evaluations').select('*').eq('rule_code', 'Dd61_15m').order('created_at', desc=True).limit(5).execute().data
    for ev in evals:
        print(f"Created At: {ev['created_at']} | Symbol: {ev['symbol']} | Score: {ev['score']} | Triggered: {ev['triggered']}")
        print(f"  Conditions: {json.dumps(ev['conditions'], indent=2)}")
        # print(f"  Context: {json.dumps(ev['context'], indent=2)}")

if __name__ == "__main__":
    asyncio.run(check_evals())
