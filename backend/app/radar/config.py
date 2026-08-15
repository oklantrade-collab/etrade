"""
Configuration for the RADAR shared signal bus.
eTrade v5.0 - Centralized Market Signals
"""
import os
from typing import Dict, Any
from app.core.logger import log_error, log_info
from app.core.supabase_client import get_supabase

MODULE = 'RADAR'

RADAR_PARAMS: Dict[str, Any] = {
    'enabled': True,
    'slope_ascending_threshold': 0.15,
    'slope_descending_threshold': -0.15,
    'slope_lookback_candles': 3,
    'adx_range_threshold': 15.0,
    'adx_trend_threshold': 30.0,
    'volume_lookback': 10,
    'volume_expansion_ratio': 1.3,
    'impulse_candle_atr_ratio': 1.8,
    'timeframes': ['15m', '1h', '4h', '1d', '5m'],
    'events_cache_path': os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'radar_events_cache.json')
}

SLOPE_THRESHOLDS = {
    'ascending': 0.15,
    'descending': -0.15
}

CROSSOVER_PAIRS = [
    ('ema_3', 'ema_9', 'cruce_EMA3_EMA9'),
    ('ema_9', 'ema_20', 'cruce_EMA9_EMA20'),
    ('ema_20', 'ema_50', 'cruce_EMA20_EMA50'),
    ('ema_50', 'ema_200', 'cruce_EMA50_EMA200'),
]


def load_radar_config_from_db() -> Dict[str, Any]:
    """
    Loads RADAR configuration overrides from the system_config table.
    """
    cfg = dict(RADAR_PARAMS)
    try:
        sb = get_supabase()
        res = sb.table('system_config').select('key, value').like('key', 'radar_%').execute()
        if res.data:
            for row in res.data:
                key = row['key'].replace('radar_', '')
                val = row['value']
                # Convert numbers or booleans if needed
                if isinstance(val, (int, float, bool)):
                    cfg[key] = val
                elif isinstance(val, str):
                    if val.lower() == 'true':
                        cfg[key] = True
                    elif val.lower() == 'false':
                        cfg[key] = False
                    else:
                        try:
                            if '.' in val:
                                cfg[key] = float(val)
                            else:
                                cfg[key] = int(val)
                        except ValueError:
                            cfg[key] = val
        log_info(MODULE, "Config loaded from database successfully.")
    except Exception as e:
        log_error(MODULE, f"Error loading config from DB (using defaults): {e}")
    return cfg
