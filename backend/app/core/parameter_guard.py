from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone
import logging

from app.core.logger import log_info, log_warning, log_error

logger = logging.getLogger('eTrader')

VELOCITY_CONFIG = {
    'debil': {
        'adx_max':       20,
        'mtf_threshold': 0.20,
        'tp_band':       'lower_2',  # target conservador
        'sl_mult':       0.5,
        'holding_max':   96,         # velas máximo
        'sizing_pct':    0.75,       # 75% del nocional
        'description':   'Mercado lento — entrar fácil, targets pequeños'
    },
    'moderado': {
        'adx_min':       20,
        'adx_max':       35,
        'mtf_threshold': 0.35,
        'tp_band':       'lower_3',
        'sl_mult':       1.0,
        'holding_max':   48,
        'sizing_pct':    1.00,
        'description':   'Mercado normal — parámetros estándar'
    },
    'agresivo': {
        'adx_min':       35,
        'adx_max':       50,
        'mtf_threshold': 0.45,
        'tp_band':       'lower_4',
        'sl_mult':       1.5,
        'holding_max':   24,
        'sizing_pct':    1.00,
        'description':   'Mercado rápido — más confirmación, targets mayores'
    },
    'explosivo': {
        'adx_min':       50,
        'mtf_threshold': 0.55,
        'tp_band':       'lower_5',
        'sl_mult':       2.0,
        'holding_max':   12,        # máximo 1 hora en 5m
        'sizing_pct':    0.75,      # reducir por riesgo
        'description':   'Mercado explosivo — muy selectivo, salir rápido'
    }
}

def get_velocity_config(adx: float) -> dict:
    """
    Retorna la configuración dinámica
    según la velocidad actual del mercado
    medida por el ADX.
    """
    if adx < 20:
        return {**VELOCITY_CONFIG['debil'],
                'velocity': 'debil'}
    elif adx < 35:
        return {**VELOCITY_CONFIG['moderado'],
                'velocity': 'moderado'}
    elif adx < 50:
        return {**VELOCITY_CONFIG['agresivo'],
                'velocity': 'agresivo'}
    else:
        return {**VELOCITY_CONFIG['explosivo'],
                'velocity': 'explosivo'}

@dataclass
class ValidationResult:
    accepted:          bool
    within_bounds:     bool
    expected_value:    Optional[float]
    reason:            str
    requires_approval: bool
    old_value:         float
    new_value:         float
    parameter_name:    str


# Mapeo explícito: nombre lógico → nombre exacto en Supabase
# NUNCA modificar estos nombres sin actualizar parameter_bounds
REGIME_PARAM_NAMES = {
    'bajo_riesgo': {
        'rr_min':        'rr_min_bajo_riesgo',
        'atr_mult':      'atr_mult_bajo_riesgo',
        'mtf_threshold': 'mtf_threshold_bajo',
        'flat_pct':      'ema20_flat_pct_bajo',
        'peak_pct':      'ema20_peak_pct_bajo',
    },
    'riesgo_medio': {
        'rr_min':        'rr_min_riesgo_medio',
        'atr_mult':      'atr_mult_riesgo_medio',
        'mtf_threshold': 'mtf_threshold_medio',
        'flat_pct':      'ema20_flat_pct_medio',
        'peak_pct':      'ema20_peak_pct_medio',
    },
    'alto_riesgo': {
        'rr_min':        'rr_min_alto_riesgo',
        'atr_mult':      'atr_mult_alto_riesgo',
        'mtf_threshold': 'mtf_threshold_alto',
        'flat_pct':      'ema20_flat_pct_alto',
        'peak_pct':      'ema20_peak_pct_alto',
    }
}

GLOBAL_PARAM_NAMES = {
    'fee_pct':             'fee_pct',
    'emergency_atr_mult':  'emergency_atr_mult',
    'signal_max_age_bars': 'signal_max_age_bars',
    'post_sl_cooldown':    'post_sl_cooldown_bars',
    'post_tp_cooldown':    'post_tp_cooldown_bars',
    'max_daily_loss_pct':  'max_daily_loss_pct',
    'max_trade_loss_pct':  'max_trade_loss_pct',
}


def calculate_expected_value(win_rate: float, avg_rr: float) -> float:
    """
    Esperanza matemática del sistema.
    EV = (win_rate × avg_rr) - (1 - win_rate)
    
    EV > 0: sistema rentable a largo plazo
    EV = 0: sistema neutro (pierde por fees)
    EV < 0: sistema perdedor
    
    Ejemplo:
      win_rate=0.50, avg_rr=2.0 → EV = (0.50×2.0) - 0.50 = +0.50  ✓
      win_rate=0.40, avg_rr=1.5 → EV = (0.40×1.5) - 0.60 = 0.00   ✗
      win_rate=0.35, avg_rr=2.5 → EV = (0.35×2.5) - 0.65 = +0.225 ✓
    """
    return round((win_rate * avg_rr) - (1 - win_rate), 4)


async def validate_parameter_change(
    parameter_name: str,
    new_value:      float,
    changed_by:     str,
    change_reason:  str,
    backtest_result: Optional[dict] = None,
    supabase_client = None
) -> ValidationResult:
    """
    Valida un cambio de parámetro contra los guardrails.

    Acepta el cambio si:
      1. El nuevo valor está dentro de los bounds definidos en Supabase
      2. Si se provee backtest_result: la esperanza matemática es positiva

    backtest_result esperado:
      {
        'win_rate':    0.55,   # 0.0 a 1.0
        'avg_rr':      2.1,    # RR promedio de los trades
        'total_trades': 15     # muestra mínima recomendada: 10 trades
      }
    """
    # Obtener bounds desde Supabase
    if supabase_client:
        result = supabase_client.table('parameter_bounds')\
            .select('*')\
            .eq('parameter_name', parameter_name)\
            .single()\
            .execute()
        bounds = result.data
    else:
        logger.warning(f'[PARAM_GUARD] Sin Supabase client, usando defaults para {parameter_name}')
        bounds = None

    if not bounds:
        return ValidationResult(
            accepted=False,
            within_bounds=False,
            expected_value=None,
            reason=f'Parámetro {parameter_name} no encontrado en parameter_bounds',
            requires_approval=True,
            old_value=0,
            new_value=new_value,
            parameter_name=parameter_name
        )

    old_value   = float(bounds['current_value'])
    min_val     = float(bounds['min_value'])
    max_val     = float(bounds['max_value'])
    within      = min_val <= new_value <= max_val

    if not within:
        # Fuera de bounds: registrar en log y bloquear
        await _log_change(
            supabase_client, parameter_name,
            old_value, new_value, changed_by, change_reason,
            within_bounds=False, accepted=False
        )
        return ValidationResult(
            accepted=False,
            within_bounds=False,
            expected_value=None,
            reason=(
                f'FUERA DE GUARDRAILS: {parameter_name} = {new_value} '
                f'no está en [{min_val}, {max_val}]. '
                f'Requiere aprobación de Jhon.'
            ),
            requires_approval=True,
            old_value=old_value,
            new_value=new_value,
            parameter_name=parameter_name
        )

    # Dentro de bounds: verificar esperanza matemática si hay backtest
    ev = None
    if backtest_result:
        win_rate     = backtest_result.get('win_rate', 0)
        avg_rr       = backtest_result.get('avg_rr', 0)
        total_trades = backtest_result.get('total_trades', 0)
        ev           = calculate_expected_value(win_rate, avg_rr)

        if total_trades < 10:
            logger.warning(
                f'[PARAM_GUARD] Muestra pequeña para {parameter_name}: '
                f'{total_trades} trades (mínimo recomendado: 10)'
            )

        if ev <= 0:
            await _log_change(
                supabase_client, parameter_name,
                old_value, new_value, changed_by, change_reason,
                within_bounds=True, accepted=False, backtest_ev=ev
            )
            return ValidationResult(
                accepted=False,
                within_bounds=True,
                expected_value=ev,
                reason=(
                    f'Dentro de guardrails pero esperanza matemática negativa: '
                    f'EV={ev:.4f} (win_rate={win_rate:.1%}, avg_rr={avg_rr:.2f}). '
                    f'El cambio no mejora la rentabilidad del sistema.'
                ),
                requires_approval=False,
                old_value=old_value,
                new_value=new_value,
                parameter_name=parameter_name
            )

    # Aceptado: actualizar current_value en Supabase
    if supabase_client:
        supabase_client.table('parameter_bounds').update({
            'current_value':    new_value,
            'last_changed_at':  datetime.now(timezone.utc).isoformat(),
            'last_changed_by':  changed_by,
            'change_reason':    change_reason,
            'perf_ev_after':    ev
        }).eq('parameter_name', parameter_name).execute()

    await _log_change(
        supabase_client, parameter_name,
        old_value, new_value, changed_by, change_reason,
        within_bounds=True, accepted=True, backtest_ev=ev
    )

    logger.info(
        f'[PARAM_GUARD] ACEPTADO: {parameter_name} '
        f'{old_value} → {new_value} | EV={ev}'
    )

    return ValidationResult(
        accepted=True,
        within_bounds=True,
        expected_value=ev,
        reason=f'Dentro de guardrails [{min_val}, {max_val}]. EV={ev}',
        requires_approval=False,
        old_value=old_value,
        new_value=new_value,
        parameter_name=parameter_name
    )


async def _log_change(sb, param_name, old_val, new_val,
                       changed_by, reason, within_bounds,
                       accepted, backtest_ev=None):
    if not sb:
        return
    try:
        sb.table('parameter_changes_log').insert({
            'parameter_name': param_name,
            'old_value':      old_val,
            'new_value':      new_val,
            'changed_by':     changed_by,
            'change_reason':  reason,
            'within_bounds':  within_bounds,
            'accepted':       accepted,
            'backtest_ev':    backtest_ev,
            'changed_at':     datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        logger.error(f'[PARAM_GUARD] Error logging change: {e}')


def get_active_params(regime: str,
                      supabase_client) -> dict:
    """
    Obtiene parámetros activos desde Supabase usando
    mapeo EXPLÍCITO de nombres. Sin split(), sin
    f-strings con lógica, sin construcción dinámica
    de nombres de claves.

    Si un parámetro no se encuentra en Supabase:
      → log WARNING visible (nunca silencioso)
      → usar fallback de CONFIG_BY_RISK_DEFAULTS
    """
    try:
        # Traer TODOS los parámetros en una sola consulta
        result = supabase_client.table('parameter_bounds')\
            .select('parameter_name, current_value')\
            .execute()

        # Índice por nombre para búsqueda O(1)
        db = {
            r['parameter_name']: float(r['current_value'])
            for r in result.data
        }

        # Obtener nombres del régimen solicitado
        regime_names = REGIME_PARAM_NAMES.get(regime)
        if not regime_names:
            log_error('PARAM_GUARD',
                f'Régimen desconocido: "{regime}". '
                f'Usando riesgo_medio como fallback.')
            regime_names = REGIME_PARAM_NAMES['riesgo_medio']

        params = {}

        # Parámetros por régimen
        for param_key, db_name in regime_names.items():
            if db_name in db:
                params[param_key] = db[db_name]
            else:
                fallback = CONFIG_BY_RISK_DEFAULTS\
                    .get(regime, {})\
                    .get(param_key, 0)
                params[param_key] = fallback
                log_warning('PARAM_GUARD',
                    f'Parametro "{db_name}" no encontrado '
                    f'en parameter_bounds. '
                    f'Usando fallback={fallback}. '
                    f'Verificar seed de parameter_bounds.')

        # Parámetros globales
        for param_key, db_name in GLOBAL_PARAM_NAMES.items():
            if db_name in db:
                params[param_key] = db[db_name]
            else:
                log_warning('PARAM_GUARD',
                    f'Parametro global "{db_name}" '
                    f'no encontrado en parameter_bounds.')

        log_info('PARAM_GUARD',
            f'Parametros cargados para {regime}: '
            f'rr_min={params.get("rr_min")} '
            f'atr_mult={params.get("atr_mult")} '
            f'mtf_threshold={params.get("mtf_threshold")}')

        return params

    except Exception as e:
        log_error('PARAM_GUARD',
            f'Error obteniendo parametros activos: {e}. '
            f'Usando fallback completo.')
        return CONFIG_BY_RISK_DEFAULTS.get(
            regime,
            CONFIG_BY_RISK_DEFAULTS['riesgo_medio']
        )


# Defaults hardcodeados como último recurso (igual al v3)
CONFIG_BY_RISK_DEFAULTS = {
    'alto_riesgo': {
        'rr_min': 3.0, 'atr_mult': 2.5, 'mtf_threshold': 0.50,
        'flat_pct': 25.0, 'peak_pct': 75.0, 'fee_pct': 0.001,
        'emergency_atr_mult': 2.0, 'signal_max_age_bars': 3,
        'post_sl_cooldown': 3, 'post_tp_cooldown': 1, 'max_daily_loss_pct': 5.0,
    },
    'riesgo_medio': {
        'rr_min': 2.5, 'atr_mult': 2.0, 'mtf_threshold': 0.35,
        'flat_pct': 20.0, 'peak_pct': 80.0, 'fee_pct': 0.001,
        'emergency_atr_mult': 2.0, 'signal_max_age_bars': 3,
        'post_sl_cooldown': 3, 'post_tp_cooldown': 1, 'max_daily_loss_pct': 5.0,
    },
    'bajo_riesgo': {
        'rr_min': 2.0, 'atr_mult': 1.5, 'mtf_threshold': 0.25,
        'flat_pct': 15.0, 'peak_pct': 85.0, 'fee_pct': 0.001,
        'emergency_atr_mult': 2.0, 'signal_max_age_bars': 3,
        'post_sl_cooldown': 3, 'post_tp_cooldown': 1, 'max_daily_loss_pct': 5.0,
    }
}
