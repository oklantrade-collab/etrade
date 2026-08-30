"""
CASCADA Module — Extended Position Manager for eTrade v5.0.
"""
from app.cascada.config import MODULE, CASCADA_PARAMS, LEVEL_DEFINITIONS, load_cascada_config_from_db
from app.cascada.cascada_engine import CascadaEngine, CascadaResult
from app.cascada.cascada_manager import CascadaManager
from app.cascada.giveback_monitor import evaluate_giveback, update_pnl_pico
from app.cascada.level_evaluator import check_rebote, check_continuacion, check_fib_zone_reversal_15m, calculate_fib_exhaustion_velocity
from app.cascada.logger import log_cascada_decision

__all__ = [
    'MODULE',
    'CASCADA_PARAMS',
    'LEVEL_DEFINITIONS',
    'load_cascada_config_from_db',
    'CascadaEngine',
    'CascadaResult',
    'CascadaManager',
    'evaluate_giveback',
    'update_pnl_pico',
    'check_rebote',
    'check_continuacion',
    'check_fib_zone_reversal_15m',
    'calculate_fib_exhaustion_velocity',
    'log_cascada_decision'
]
