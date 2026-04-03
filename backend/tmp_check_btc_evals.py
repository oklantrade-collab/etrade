import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def check_evals():
    sb = get_supabase()
    evals = sb.table('strategy_evaluations').select('*').eq('symbol', 'BTC/USDT').order('created_at', desc=True).limit(20).execute().data
    for ev in evals:
        print(f"Time: {ev['created_at']} | Rule: {ev['rule_code']} | Score: {ev['score']} | Triggered: {ev['triggered']}")
        if ev['triggered']:
             print(f"  Conditions: {json.dumps(ev['conditions'], indent=2)}")

if __name__ == "__main__":
    asyncio.run(check_evals())
