import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def insert_config():
    sb = get_supabase()
    
    configs = [
        {'id': 101, 'key': 'erep_enabled_crypto', 'value': 'true'},
        {'id': 102, 'key': 'erep_enabled_forex', 'value': 'true'},
        {'id': 103, 'key': 'erep_max_loss_pct_crypto', 'value': '6.0'},
        {'id': 104, 'key': 'erep_max_loss_pct_forex', 'value': '1.5'},
        {'id': 105, 'key': 'erep_timeout_cycles', 'value': '4'},
        {'id': 106, 'key': 'erep_p2_size_factor', 'value': '1.0'},
        {'id': 107, 'key': 'erep_max_sar_4h_bearish', 'value': 'false'},
        {'id': 108, 'key': 'erep_max_drop_pct', 'value': '5.0'},
    ]
    
    print("Inserting EREP trading configs...")
    for cfg in configs:
        try:
            print(f"Upserting key: {cfg['key']}")
            # Manual delete to emulate upsert
            sb.table('trading_config').delete().eq('key', cfg['key']).execute()
            sb.table('trading_config').insert(cfg).execute()
            print("  OK")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    insert_config()
