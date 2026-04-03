import os
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timezone, timedelta
from collections import defaultdict

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'),
                   os.getenv('SUPABASE_SERVICE_KEY'))

async def check():
    print("--- Verificando Frankfurt post-deploy ---")
    cutoff = (datetime.now(timezone.utc) - 
              timedelta(minutes=60)).isoformat() # 60 min to be safe

    res = sb.table('pilot_diagnostics')\
        .select('symbol, cycle_type, timestamp')\
        .gte('timestamp', cutoff)\
        .order('timestamp', desc=True)\
        .execute()

    by_symbol = defaultdict(set)
    for r in res.data:
        by_symbol[r['symbol']].add(r['cycle_type'])

    print("Frankfurt post-deploy:")
    for sym, cycles in sorted(by_symbol.items()):
        print(f"  {sym:8} -> {list(cycles)}")

    expected = {'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT'}
    missing  = expected - set(by_symbol.keys())
    print(f"\nFaltantes: {missing if missing else 'Ninguno - OK'}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(check())
