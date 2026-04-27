import asyncio, os, sys
sys.path.append('c:\\Fuentes\\eTrade\\backend')
from app.core.supabase_client import get_supabase

def run():
    sb = get_supabase()
    res = sb.table('market_snapshot').select('symbol, upper_1, lower_1, upper_3, lower_3').eq('symbol', 'GBPUSD').execute()
    for r in res.data:
        print(f"{r['symbol']} | U1: {r['upper_1']} | L1: {r['lower_1']} | U3: {r['upper_3']} | L3: {r['lower_3']}")

if __name__ == '__main__':
    run()
