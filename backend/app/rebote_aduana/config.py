import pandas as pd
from app.core.logger import log_error
from app.core.supabase_client import get_supabase

MODULE = 'REBOTE_ADUANA'

REBOTE_PARAMS = {
    'score_min_entry': 50,
    'score_min_additional': 70,
    'w_fib_extreme_6': 40,
    'w_double_bottom_top': 35,
    'w_ema_squeeze_bb': 25,
    'w_rsi_extreme_structure': 25,
    'w_zone_confluence': 15,
    'adx_range_threshold': 15.0,
    'adx_trend_threshold': 30.0,
    'adx_range_multiplier': 1.2,
    'adx_trend_multiplier': 0.5,
    'volume_expansion_ratio': 1.3,
    'volume_lookback': 10,
    'volume_bonus_multiplier': 1.1,
    'regime_tf': '15m'
}

ADUANA_PARAMS = {
    'impulse_candle_atr_ratio': 1.8,
    'extreme_proximity_zones': 3,
    'range_bb_bandwidth_threshold': 0.02,
    'macro_score_threshold': 30.0
}

def load_rebote_config_from_db() -> dict:
    """Loads Rebote/Aduana configuration from Supabase system_config table."""
    try:
        supabase = get_supabase()
        if not supabase:
            return {}
            
        response = supabase.table('system_config').select('*').like('key', 'rebote_%').execute()
        if response and hasattr(response, 'data') and response.data:
            config = {}
            for row in response.data:
                config[row['key']] = row['value']
            return config
        return {}
    except Exception as e:
        log_error(f"Error loading {MODULE} config from DB: {e}")
        return {}
