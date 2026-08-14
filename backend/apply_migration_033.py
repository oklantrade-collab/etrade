"""
Apply Migration 033: HALCÓN CENTINELA tables & config.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

DEFAULT_CONFIGS = [
    ('halcon_enabled', 'true'),
    ('halcon_min_profit_usd', '1.0'),
    ('halcon_partial_close_pct', '0.50'),
    ('halcon_adx_range_threshold', '15'),
    ('halcon_adx_trend_threshold', '30'),
    ('halcon_compression_threshold', '0.15'),
    ('halcon_volume_multiplier', '1.3'),
    ('halcon_volume_lookback', '10'),
    ('halcon_atr_pct_threshold', '0.008'),
    ('halcon_rsi_extreme_low', '20'),
    ('halcon_rsi_extreme_high', '80'),
    ('halcon_rsi_extreme_points', '25'),
    ('halcon_rsi_divergence_points', '35'),
    ('halcon_ema_proximity_pct', '0.15'),
    ('halcon_oraculo_enabled', 'true'),
    ('halcon_oraculo_pre_event_min', '60'),
    ('halcon_oraculo_post_event_min', '60'),
    ('halcon_oraculo_close_pnl_threshold', '-5.0'),
    ('halcon_oraculo_bracket_sl_floor', '-8.0'),
    ('halcon_oraculo_calendar_sync_min', '60')
]

def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 1. Apply system_config defaults
    print("Applying system_config HALCÓN parameters...")
    for key, value in DEFAULT_CONFIGS:
        try:
            sb.table('system_config').upsert({'key': key, 'value': value}).execute()
            print(f"  [OK] {key} = {value}")
        except Exception as e:
            print(f"  [ERROR] {key}: {e}")

    # 2. Try executing DDL via exec_sql RPC if available
    sql_path = os.path.join(os.path.dirname(__file__), "migration_033_halcon_centinela.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    try:
        sb.rpc("exec_sql", {"sql_text": sql}).execute()
        print("[OK] Migration 033 SQL applied via RPC exec_sql")
    except Exception as e:
        print(f"[INFO] RPC exec_sql not available ({e}).")
        # Check if tables exist
        for tbl in ['halcon_scores_log', 'centinela_decisions_log', 'oraculo_events', 'centinela_position_state']:
            try:
                sb.table(tbl).select('id').limit(1).execute()
                print(f"  [OK] Table '{tbl}' verified.")
            except Exception as e2:
                print(f"  [NOTE] Table '{tbl}' not created via SDK. DDL statements in migration_033_halcon_centinela.sql can be executed in Supabase SQL Editor.")

if __name__ == "__main__":
    main()
