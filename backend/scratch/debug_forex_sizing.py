import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')
load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

from app.core.position_sizing import calculate_position_size

def run():
    print("=== TESTING REAL FOREX POSITION SIZING ===")
    
    # Let's check trading_config values in Supabase
    cfg = sb.table('trading_config').select('*').eq('id', 1).single().execute()
    print("Trading Config:")
    print(f"  capital_forex_futures: {cfg.data.get('capital_forex_futures')}")
    print(f"  leverage_forex: {cfg.data.get('leverage_forex')}")
    
    # Check risk_config
    rc = sb.table('risk_config').select('*').limit(1).execute()
    if rc.data:
        print(f"Risk Config max_risk_per_trade_pct: {rc.data[0].get('max_risk_per_trade_pct')}")
        
    entry_price = 1.34223
    sl_price = entry_price * 1.005 # SHORT SL (0.5% distance)
    
    res = calculate_position_size(
        symbol="GBPUSD",
        entry_price=entry_price,
        sl_price=sl_price,
        market_type="forex_futures",
        trade_number=1,
        regime="swing",
        supabase=sb
    )
    
    print("\nResulting Sizing Dictionary:")
    for k, v in res.items():
        print(f"  {k}: {v}")

if __name__ == '__main__':
    run()
