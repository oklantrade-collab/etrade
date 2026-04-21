import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def list_all_symbols():
    sb = get_supabase()
    tables = ['forex_positions', 'positions', 'paper_trades', 'orders', 'market_snapshot', 'market_candles']
    all_syms = {}
    for t in tables:
        try:
            res = sb.table(t).select('symbol').execute()
            syms = set(r['symbol'] for r in res.data if r.get('symbol'))
            all_syms[t] = sorted(list(syms))
        except Exception as e:
            all_syms[t] = f"Error: {e}"
    
    print(json.dumps(all_syms, indent=2))

if __name__ == "__main__":
    asyncio.run(list_all_symbols())
