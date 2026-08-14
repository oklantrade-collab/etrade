from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from enum import Enum
from app.core.logger import log_error
from app.core.supabase_client import get_supabase

MODULE = 'HALCON_CENTINELA'

class EntryProfile(Enum):
    ALTA_VOLATILIDAD = 'ALTA_VOLATILIDAD'
    TENDENCIA_SOSTENIDA = 'TENDENCIA_SOSTENIDA'

@dataclass
class HalconProfile:
    """Perfil de monitoreo por posición."""
    name: str
    weights: Dict[str, float]  # {1d, 4h, 15m, 5m, 1m}
    close_threshold: float     # ±score para cierre total
    partial_threshold_low: float  # rango inferior cierre parcial
    partial_threshold_high: float # rango superior cierre parcial
    cooldown_seconds: int
    monitor_interval_seconds: float
    rsi_reduce_in_strong_trend: bool

PERFIL_ALTA_VOLATILIDAD = HalconProfile(
    name='ALTA_VOLATILIDAD',
    weights={'1d': 10.0, '4h': 15.0, '15m': 25.0, '5m': 25.0, '1m': 25.0},
    close_threshold=45.0,
    partial_threshold_low=25.0,
    partial_threshold_high=45.0,
    cooldown_seconds=120,
    monitor_interval_seconds=15.0,
    rsi_reduce_in_strong_trend=False
)

PERFIL_TENDENCIA_SOSTENIDA = HalconProfile(
    name='TENDENCIA_SOSTENIDA',
    weights={'1d': 30.0, '4h': 25.0, '15m': 20.0, '5m': 15.0, '1m': 10.0},
    close_threshold=60.0,
    partial_threshold_low=25.0,
    partial_threshold_high=60.0,
    cooldown_seconds=900,
    monitor_interval_seconds=30.0,
    rsi_reduce_in_strong_trend=True
)

HALCON_PARAMS = {
    'adx_range_threshold': 15.0,
    'adx_trend_threshold': 30.0,
    'compression_threshold': 0.15,
    'volume_confirmation_multiplier': 1.3,
    'volume_lookback': 10,
    'atr_pct_volatility_threshold': 0.008,
    'rsi_extreme_low': 20.0,
    'rsi_extreme_high': 80.0,
    'rsi_extreme_points': 25.0,
    'rsi_divergence_points': 35.0,
    'min_profit_usd': 1.0,
    'partial_close_pct': 0.50,
    'ema_proximity_threshold_atr_pct': 0.15
}

ORACULO_PARAMS = {
    'pre_event_window_minutes': 60,
    'post_event_window_minutes': 60,
    'min_impact_level': 'high',
    'market_close_pnl_threshold': -5.0,
    'bracket_sl_floor_usd': -8.0,
    'calendar_sync_interval_minutes': 60
}

SYMBOL_CURRENCY_MAP = {
    'USDJPY': ['USD', 'JPY'],
    'XAUUSD': ['USD'],
    'EURUSD': ['EUR', 'USD'],
    'GBPUSD': ['GBP', 'USD'],
    'BTCUSD': ['USD'],
    'BTCUSDT': ['USD'],
    'ETHUSDT': ['USD'],
}

GLOBAL_EVENTS = ['FOMC', 'NFP', 'CPI', 'BOJ_RATE', 'ECB_RATE', 'BOE_RATE']

class Semaforo(Enum):
    ROJO_FUERTE = 'rojo_fuerte'
    ROJO_DEBIL = 'rojo_debil'
    AMBAR = 'ambar'
    VERDE_DEBIL = 'verde_debil'
    VERDE_FUERTE = 'verde_fuerte'

class CentinelaDecision(Enum):
    CIERRE_TOTAL = 'CIERRE_TOTAL'
    CIERRE_PARCIAL = 'CIERRE_PARCIAL'
    MANTENER = 'MANTENER'

def get_profile(entry_profile: str) -> HalconProfile:
    """Returns the profile config for the given entry_profile string."""
    if entry_profile.upper() == EntryProfile.ALTA_VOLATILIDAD.value:
        return PERFIL_ALTA_VOLATILIDAD
    return PERFIL_TENDENCIA_SOSTENIDA

def classify_entry_profile(adx: float, atr_pct_daily: float) -> EntryProfile:
    """Classifies entry profile based on ADX and ATR% at position open time.
    ALTA_VOLATILIDAD: adx > 30 AND atr_pct > 0.8%
    Otherwise: TENDENCIA_SOSTENIDA
    """
    if adx > HALCON_PARAMS['adx_trend_threshold'] and atr_pct_daily > HALCON_PARAMS['atr_pct_volatility_threshold']:
        return EntryProfile.ALTA_VOLATILIDAD
    return EntryProfile.TENDENCIA_SOSTENIDA

def load_halcon_config_from_db() -> Dict[str, Any]:
    """Loads HALCON parameter overrides from system_config table.
    Keys prefixed with 'halcon_' in system_config.
    Returns merged dict of defaults + DB overrides.
    """
    merged_config = HALCON_PARAMS.copy()
    try:
        supabase = get_supabase()
        response = supabase.table('system_config').select('*').like('key', 'halcon_%').execute()
        
        if response.data:
            for item in response.data:
                key = item['key'].replace('halcon_', '')
                if key in merged_config:
                    merged_config[key] = float(item['value']) if isinstance(merged_config[key], float) else type(merged_config[key])(item['value'])
                    
    except Exception as e:
        log_error(f"Failed to load HALCON config from DB: {str(e)}", MODULE)
        
    return merged_config
