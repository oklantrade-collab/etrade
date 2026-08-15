"""
Configuration for CASCADA Position Manager in Extension.
eTrade v5.0 — Spec Section 3 & 5
"""
from typing import Dict, Any
from app.core.logger import log_error, log_info
from app.core.supabase_client import get_supabase

MODULE = 'CASCADA'

CASCADA_PARAMS: Dict[str, Any] = {
    'enabled': True,
    'giveback_threshold_pct': 0.50,         # 50% max giveback from peak PnL
    'slope_ascending_threshold': 0.15,
    'slope_descending_threshold': -0.15,
    'support_signal_bb_tf': '15m',          # Bollinger upper/lower band flattening
    'support_signal_hh_tf_n1': '15m',       # Highs descending TF for N1
    'support_signal_hh_tf_n2_n5': '1h',     # Highs descending TF for N2-N5 (proxy for 30m)
    'hh_lookback_candles': 3,               # Last 3 closed candles
    'max_cascade_level': 5,
}

LEVEL_DEFINITIONS = {
    0: {'name': 'N0', 'event': 'entry_rebote', 'desc': 'Entrada en extremo (REBOTE/ADUANA)'},
    1: {'name': 'N1', 'event': 'cruce_EMA3_EMA9', 'desc': 'Cruce EMA3/EMA9 en 15m'},
    2: {'name': 'N2', 'event': 'cruce_EMA9_EMA20', 'desc': 'Cruce EMA9/EMA20 en 15m'},
    3: {'name': 'N3', 'event': 'cruce_EMA20_EMA50', 'desc': 'Cruce EMA20/EMA50 en 15m'},
    4: {'name': 'N4', 'event': 'cruce_EMA50_EMA200', 'desc': 'Cruce EMA50/EMA200 en 15m'},
    5: {'name': 'N5', 'event': 'cruce_fibonacci_sucesivo', 'desc': 'Cruces Fibonacci sucesivos'}
}


def load_cascada_config_from_db() -> Dict[str, Any]:
    """
    Loads CASCADA configuration overrides from system_config table.
    """
    cfg = dict(CASCADA_PARAMS)
    try:
        sb = get_supabase()
        res = sb.table('system_config').select('key, value').like('key', 'cascada_%').execute()
        if res.data:
            for row in res.data:
                key = row['key'].replace('cascada_', '')
                val = row['value']
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
