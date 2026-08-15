"""
RADAR Module — Shared Signal Bus for eTrade v5.0.
"""
from app.radar.config import MODULE, RADAR_PARAMS, SLOPE_THRESHOLDS, CROSSOVER_PAIRS, load_radar_config_from_db
from app.radar.slope_classifier import classify_slope, get_slope_matrix_interpretation
from app.radar.crossover_detector import (
    detect_ema_crossovers, 
    detect_fibonacci_crossover, 
    detect_impulse_candle
)
from app.radar.event_bus import RadarEventBus
from app.radar.radar_service import RadarService
from app.radar.logger import log_radar_event

__all__ = [
    'MODULE',
    'RADAR_PARAMS',
    'SLOPE_THRESHOLDS',
    'CROSSOVER_PAIRS',
    'load_radar_config_from_db',
    'classify_slope',
    'get_slope_matrix_interpretation',
    'detect_ema_crossovers',
    'detect_fibonacci_crossover',
    'detect_impulse_candle',
    'RadarEventBus',
    'RadarService',
    'log_radar_event'
]
