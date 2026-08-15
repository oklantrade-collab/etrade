"""
Apply Migration 035: RADAR and CASCADA schema & configurations.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

DEFAULT_CONFIGS = [
    ('radar_enabled', 'true'),
    ('radar_slope_ascending_threshold', '0.15'),
    ('radar_slope_descending_threshold', '-0.15'),
    ('radar_slope_lookback_candles', '3'),
    ('cascada_enabled', 'true'),
    ('cascada_giveback_threshold_pct', '0.50'),
    ('cascada_support_signal_bb_tf', '15m'),
    ('cascada_support_signal_hh_tf_n1', '15m'),
    ('cascada_support_signal_hh_tf_n2_n5', '1h'),
    ('rebote_enabled', 'true'),
    ('rebote_score_min_entry', '50'),
    ('rebote_score_min_additional', '70'),
    ('aduana_enabled', 'true'),
    ('aduana_impulse_atr_ratio', '1.8')
]

def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    print("Applying system_config RADAR & CASCADA parameters...")
    for key, value in DEFAULT_CONFIGS:
        try:
            sb.table('system_config').upsert({'key': key, 'value': value}).execute()
            print(f"  [OK] {key} = {value}")
        except Exception as e:
            print(f"  [ERROR] {key}: {e}")

    # Try applying DDL via exec_sql RPC
    sql_path = os.path.join(os.path.dirname(__file__), "migration_035_radar_cascada.sql")
    if os.path.exists(sql_path):
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()

        try:
            sb.rpc("exec_sql", {"sql_text": sql}).execute()
            print("[OK] Migration 035 SQL applied via RPC exec_sql")
        except Exception as e:
            print(f"[INFO] RPC exec_sql returned: {e}")

if __name__ == '__main__':
    main()
