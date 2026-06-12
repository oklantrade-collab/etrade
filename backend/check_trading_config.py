import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_config():
    sb = get_supabase()
    
    print("--- 1. trading_config (id=1) ---")
    cfg = sb.table('trading_config').select('*').eq('id', 1).single().execute()
    if cfg.data:
        for k, v in cfg.data.items():
            print(f"  {k}: {v}")
    else:
        print("No trading_config row found (id=1)")
        
    print("\n--- 2. risk_config ---")
    risk = sb.table('risk_config').select('*').limit(1).execute()
    if risk.data:
        for k, v in risk.data[0].items():
            print(f"  {k}: {v}")
    else:
        print("No risk_config row found")
        
    print("\n--- 3. strategy_variables ---")
    try:
        vars = sb.table('strategy_variables').select('*').execute()
        print(f"Total strategy variables: {len(vars.data)}")
    except Exception as e:
        print(f"Error reading strategy_variables: {e}")

if __name__ == "__main__":
    check_config()
