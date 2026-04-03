import os
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timezone, timedelta
from collections import defaultdict

load_dotenv()
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

async def verify_phase_0():
    # Verificar heartbeats de los 4 símbolos en los últimos 30 minutos
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()

    res = sb.table('pilot_diagnostics')\
        .select('symbol, cycle_type, rule_evaluated, timestamp')\
        .gte('timestamp', cutoff)\
        .order('timestamp', desc=True)\
        .execute()

    # Agrupar por símbolo
    by_symbol = defaultdict(list)
    for r in res.data:
        by_symbol[r['symbol']].append(r['cycle_type'])

    print("Simbolos activos en los ultimos 30 minutos:")
    for sym, cycles in sorted(by_symbol.items()):
        print(f"  {sym:8} -> ciclos: {set(cycles)}")

    expected = {'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT'}
    active   = set(by_symbol.keys())
    missing  = expected - active
    print(f"\nEsperados: {expected}")
    print(f"Activos:   {active}")
    print(f"Faltantes: {missing if missing else 'Ninguno - OK'}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(verify_phase_0())
