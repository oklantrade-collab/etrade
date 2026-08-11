import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check_sizing():
    sb = get_supabase()
    res = sb.table('trading_config').select('*').eq('id', 1).execute()
    if res.data:
        cfg = res.data[0]
        print("=== CONFIGURACIÓN DE APALANCAMIENTO Y CAPITAL EN ETRADE ===")
        print(f"Capital Crypto Futures: ${cfg.get('capital_crypto_futures')}")
        print(f"Capital Operativo: ${cfg.get('capital_operativo')}")
        print(f"Leverage Crypto: {cfg.get('leverage_crypto')}x")
        print(f"Active Symbols: {cfg.get('active_symbols')}")

if __name__ == "__main__":
    check_sizing()
