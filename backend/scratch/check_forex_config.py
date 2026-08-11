import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check_forex():
    sb = get_supabase()
    res = sb.table('trading_config').select('*').eq('id', 1).execute()
    if res.data:
        cfg = res.data[0]
        print("=== CONFIGURACIÓN FOREX EN TRADING_CONFIG ===")
        print(f"Capital Forex Futures/Spot: ${cfg.get('capital_forex_futures')}")
        print(f"Leverage Forex: {cfg.get('leverage_forex')}")
        print(f"Forex Assets: {cfg.get('regime_params', {}).get('forex_assets')}")

if __name__ == "__main__":
    check_forex()
