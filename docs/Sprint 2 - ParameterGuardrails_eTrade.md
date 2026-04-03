# 🛡️ ENGINEERING BRIEF — Parameter Guardrails System
## Proyecto: eTrade | Destino: Antigravity Dev Team
**Complemento al:** PROMPT_ANTIGRAVITY_eTrade_v3.md  
**Fecha:** Marzo 2026 | **Prioridad:** Alta — implementar junto con backtesting module

---

## 1. OBJETIVO

Implementar un sistema de **guardrails de parámetros** que:

1. Define rangos seguros para todos los parámetros críticos de riesgo
2. Permite a Antigravity ajustar parámetros libremente **dentro** del rango sin aprobación
3. Bloquea cualquier cambio **fuera** del rango y genera alerta para aprobación de Jhon
4. Valida que todo cambio muestre **esperanza matemática positiva** en backtesting antes de aceptarse

**Regla fundamental:** Ningún cambio a parámetros de riesgo (rr_min, atr_mult, umbrales de régimen) puede implementarse sin pasar por este sistema, sin importar el contexto técnico en que ocurra.

---

## 2. TABLA DE GUARDRAILS

### 2.1 Schema SQL

```sql
-- Tabla de límites por parámetro
CREATE TABLE IF NOT EXISTS parameter_bounds (
    parameter_name      VARCHAR(50)  PRIMARY KEY,
    category            VARCHAR(20)  NOT NULL,
    -- Valores: 'risk' | 'entry' | 'sizing' | 'timing' | 'technical'

    min_value           NUMERIC(10,4) NOT NULL,
    max_value           NUMERIC(10,4) NOT NULL,
    default_value       NUMERIC(10,4) NOT NULL,
    current_value       NUMERIC(10,4) NOT NULL,

    description         TEXT,
    unit                VARCHAR(20),    -- 'ratio' | 'multiplier' | 'pct' | 'bars' | 'float'
    regime              VARCHAR(20),    -- 'bajo_riesgo' | 'riesgo_medio' | 'alto_riesgo' | 'all'

    requires_approval_outside_bounds  BOOLEAN DEFAULT true,
    last_changed_at     TIMESTAMPTZ DEFAULT NOW(),
    last_changed_by     VARCHAR(50),    -- 'system' | 'antigravity' | 'jhon'
    change_reason       TEXT,

    -- Performance al momento del último cambio
    perf_win_rate_before    NUMERIC(5,4),
    perf_win_rate_after     NUMERIC(5,4),
    perf_ev_before          NUMERIC(8,4),   -- expected value antes del cambio
    perf_ev_after           NUMERIC(8,4),   -- expected value después del cambio

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Historial de todos los cambios (audit trail)
CREATE TABLE IF NOT EXISTS parameter_changes_log (
    id              BIGSERIAL PRIMARY KEY,
    parameter_name  VARCHAR(50) REFERENCES parameter_bounds(parameter_name),
    old_value       NUMERIC(10,4),
    new_value       NUMERIC(10,4),
    changed_at      TIMESTAMPTZ DEFAULT NOW(),
    changed_by      VARCHAR(50),
    change_reason   TEXT,
    within_bounds   BOOLEAN,
    approved_by     VARCHAR(50),    -- null si dentro de bounds, 'jhon' si fuera
    backtest_ev     NUMERIC(8,4),   -- expected value del backtest que justificó el cambio
    accepted        BOOLEAN
);
```

### 2.2 Seed inicial — valores del documento v3

```sql
INSERT INTO parameter_bounds
    (parameter_name, category, min_value, max_value, default_value, current_value,
     description, unit, regime)
VALUES

-- ═══ PARÁMETROS DE RIESGO (RR mínimo) ═══
('rr_min_bajo_riesgo',     'risk', 1.5, 4.0, 2.0, 2.0,
 'RR mínimo aceptable en régimen bajo riesgo. < 1.5 destruye esperanza matemática con 50% win rate.',
 'ratio', 'bajo_riesgo'),

('rr_min_riesgo_medio',    'risk', 1.5, 4.0, 2.5, 2.5,
 'RR mínimo aceptable en régimen riesgo medio. Mayor que bajo_riesgo para compensar el mayor ATR.',
 'ratio', 'riesgo_medio'),

('rr_min_alto_riesgo',     'risk', 2.0, 4.0, 3.0, 3.0,
 'RR mínimo aceptable en régimen alto riesgo. El más exigente por la mayor volatilidad.',
 'ratio', 'alto_riesgo'),

-- ═══ PARÁMETROS DE RIESGO (SL — multiplicador ATR) ═══
('atr_mult_bajo_riesgo',   'risk', 1.0, 3.5, 1.5, 1.5,
 'Multiplicador del ATR para calcular el Stop Loss en bajo riesgo. SL = entry - (ATR × mult).',
 'multiplier', 'bajo_riesgo'),

('atr_mult_riesgo_medio',  'risk', 1.0, 3.5, 2.0, 2.0,
 'Multiplicador del ATR para calcular el Stop Loss en riesgo medio.',
 'multiplier', 'riesgo_medio'),

('atr_mult_alto_riesgo',   'risk', 1.0, 3.5, 2.5, 2.5,
 'Multiplicador del ATR para calcular el Stop Loss en alto riesgo.',
 'multiplier', 'alto_riesgo'),

-- ═══ PARÁMETROS DE ENTRADA (MTF threshold) ═══
('mtf_threshold_bajo',     'entry', 0.45, 0.90, 0.50, 0.50,
 'Umbral de alineación multi-timeframe en bajo riesgo. Al menos 50% de TFs alineados.',
 'pct', 'bajo_riesgo'),

('mtf_threshold_medio',    'entry', 0.45, 0.90, 0.65, 0.65,
 'Umbral de alineación multi-timeframe en riesgo medio. Al menos 65% de TFs alineados.',
 'pct', 'riesgo_medio'),

('mtf_threshold_alto',     'entry', 0.45, 0.90, 0.80, 0.80,
 'Umbral de alineación multi-timeframe en alto riesgo. Al menos 80% de TFs alineados.',
 'pct', 'alto_riesgo'),

-- ═══ PARÁMETROS TÉCNICOS (EMA20 phases) ═══
('ema20_flat_pct_bajo',    'technical', 10.0, 30.0, 15.0, 15.0,
 'Percentil que define zona plana del EMA20 en bajo riesgo.',
 'pct', 'bajo_riesgo'),

('ema20_flat_pct_medio',   'technical', 10.0, 30.0, 20.0, 20.0,
 'Percentil que define zona plana del EMA20 en riesgo medio.',
 'pct', 'riesgo_medio'),

('ema20_flat_pct_alto',    'technical', 10.0, 30.0, 25.0, 25.0,
 'Percentil que define zona plana del EMA20 en alto riesgo.',
 'pct', 'alto_riesgo'),

('ema20_peak_pct_bajo',    'technical', 70.0, 90.0, 85.0, 85.0,
 'Percentil que define zona de cima del EMA20 en bajo riesgo.',
 'pct', 'bajo_riesgo'),

('ema20_peak_pct_medio',   'technical', 70.0, 90.0, 80.0, 80.0,
 'Percentil que define zona de cima del EMA20 en riesgo medio.',
 'pct', 'riesgo_medio'),

('ema20_peak_pct_alto',    'technical', 70.0, 90.0, 75.0, 75.0,
 'Percentil que define zona de cima del EMA20 en alto riesgo.',
 'pct', 'alto_riesgo'),

-- ═══ PARÁMETROS DE TIMING (cooldown y holding) ═══
('post_sl_cooldown_bars',  'timing', 1, 10, 3, 3,
 'Velas de cooldown después de un SL. Evita revenge trading automático.',
 'bars', 'all'),

('post_tp_cooldown_bars',  'timing', 0, 5,  1, 1,
 'Velas de cooldown después de un TP.',
 'bars', 'all'),

('signal_max_age_bars',    'timing', 1, 10, 3, 3,
 'Máximo de barras que puede tener una señal del PineScript antes de expirar.',
 'bars', 'all'),

-- ═══ PARÁMETROS DE SIZING ═══
('capital_pct_for_trading','sizing', 5.0, 50.0, 20.0, 20.0,
 '% del capital total destinado a trading. El 80% restante permanece como reserva.',
 'pct', 'all'),

('fee_pct',                'sizing', 0.001, 0.002, 0.001, 0.001,
 'Fee estimado de Binance por operación (0.1% maker/taker).',
 'float', 'all'),

-- ═══ PROTECCIONES DE RIESGO ═══
('max_daily_loss_pct',     'risk', 2.0, 15.0, 5.0, 5.0,
 '% máximo de pérdida diaria sobre capital total antes de activar circuit breaker.',
 'pct', 'all'),

('max_trade_loss_pct',     'risk', 0.5, 5.0, 2.0, 2.0,
 '% máximo de pérdida por trade individual sobre capital total.',
 'pct', 'all'),

('emergency_atr_mult',     'risk', 1.5, 4.0, 2.0, 2.0,
 'Multiplicador del ATR promedio que activa el monitor de emergencia vía WebSocket.',
 'multiplier', 'all')

ON CONFLICT (parameter_name) DO NOTHING;
```

---

## 3. FUNCIÓN DE VALIDACIÓN (Python)

### 3.1 Módulo: `app/core/parameter_guard.py`

```python
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger('eTrader')

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
            'last_changed_at':  datetime.utcnow().isoformat(),
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
            'changed_at':     datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f'[PARAM_GUARD] Error logging change: {e}')


def get_active_params(regime: str, supabase_client) -> dict:
    """
    Obtiene los valores ACTUALES de todos los parámetros para un régimen.
    El scheduler debe usar esta función en lugar de CONFIG_BY_RISK hardcodeado.

    Retorna dict compatible con el existente CONFIG_BY_RISK del v3.
    """
    try:
        result = supabase_client.table('parameter_bounds')\
            .select('parameter_name, current_value')\
            .in_('regime', [regime, 'all'])\
            .execute()

        params = {r['parameter_name']: float(r['current_value'])
                  for r in result.data}

        # Mapear a la estructura esperada por el scheduler
        return {
            'rr_min':             params.get(f'rr_min_{regime}', 2.0),
            'atr_mult':           params.get(f'atr_mult_{regime}', 2.0),
            'mtf_threshold':      params.get(f'mtf_threshold_{regime.split("_")[0]}', 0.65),
            'flat_pct':           params.get(f'ema20_flat_pct_{regime}', 20.0),
            'peak_pct':           params.get(f'ema20_peak_pct_{regime}', 80.0),
            'fee_pct':            params.get('fee_pct', 0.001),
            'emergency_atr_mult': params.get('emergency_atr_mult', 2.0),
            'signal_max_age_bars':params.get('signal_max_age_bars', 3),
            'post_sl_cooldown':   params.get('post_sl_cooldown_bars', 3),
            'post_tp_cooldown':   params.get('post_tp_cooldown_bars', 1),
            'max_daily_loss_pct': params.get('max_daily_loss_pct', 5.0),
        }
    except Exception as e:
        logger.error(f'[PARAM_GUARD] Error obteniendo parámetros activos: {e}')
        # Fallback a los defaults del v3 si Supabase no responde
        return CONFIG_BY_RISK_DEFAULTS.get(regime, CONFIG_BY_RISK_DEFAULTS['riesgo_medio'])


# Defaults hardcodeados como último recurso (igual al v3)
CONFIG_BY_RISK_DEFAULTS = {
    'alto_riesgo': {
        'rr_min': 3.0, 'atr_mult': 2.5, 'mtf_threshold': 0.80,
        'flat_pct': 25.0, 'peak_pct': 75.0, 'fee_pct': 0.001,
        'emergency_atr_mult': 2.0, 'signal_max_age_bars': 3,
        'post_sl_cooldown': 3, 'post_tp_cooldown': 1, 'max_daily_loss_pct': 5.0,
    },
    'riesgo_medio': {
        'rr_min': 2.5, 'atr_mult': 2.0, 'mtf_threshold': 0.65,
        'flat_pct': 20.0, 'peak_pct': 80.0, 'fee_pct': 0.001,
        'emergency_atr_mult': 2.0, 'signal_max_age_bars': 3,
        'post_sl_cooldown': 3, 'post_tp_cooldown': 1, 'max_daily_loss_pct': 5.0,
    },
    'bajo_riesgo': {
        'rr_min': 2.0, 'atr_mult': 1.5, 'mtf_threshold': 0.50,
        'flat_pct': 15.0, 'peak_pct': 85.0, 'fee_pct': 0.001,
        'emergency_atr_mult': 2.0, 'signal_max_age_bars': 3,
        'post_sl_cooldown': 3, 'post_tp_cooldown': 1, 'max_daily_loss_pct': 5.0,
    }
}
```

---

## 4. INTEGRACIÓN CON EL SCHEDULER

### 4.1 Cambio en `scheduler.py`

El scheduler debe obtener los parámetros activos desde Supabase en lugar de usar el dict hardcodeado `CONFIG_BY_RISK`:

```python
# ANTES (hardcodeado — eliminar):
# cfg = CONFIG_BY_RISK[regime['category']]

# DESPUÉS (dinámico desde Supabase):
from app.core.parameter_guard import get_active_params
cfg = get_active_params(regime['category'], supabase_client)
```

### 4.2 Cambio en `backtester.py`

El backtester también debe usar `get_active_params` para que los backtest reflejen los parámetros actuales:

```python
from app.core.parameter_guard import get_active_params, validate_parameter_change

# Al inicio del backtest, obtener parámetros activos:
active_params = get_active_params(regime_category, supabase_client)
rr_min  = active_params['rr_min']
atr_mult= active_params['atr_mult']
```

### 4.3 Uso en backtesting para validar un cambio propuesto

```python
# Ejemplo: Antigravity propone cambiar rr_min_riesgo_medio de 2.5 a 2.2
result = await validate_parameter_change(
    parameter_name  = 'rr_min_riesgo_medio',
    new_value       = 2.2,
    changed_by      = 'antigravity',
    change_reason   = 'Aumentar frecuencia de trades en riesgo medio',
    backtest_result = {
        'win_rate':     0.58,
        'avg_rr':       2.3,
        'total_trades': 22
    },
    supabase_client = supabase
)

if result.accepted:
    print(f'Cambio aceptado. EV={result.expected_value}')
    # El parámetro ya fue actualizado en Supabase por validate_parameter_change
else:
    print(f'Cambio rechazado: {result.reason}')
    if result.requires_approval:
        await send_telegram(
            f'⚠️ APROBACIÓN REQUERIDA\n'
            f'Parámetro: {result.parameter_name}\n'
            f'Valor propuesto: {result.new_value} '
            f'(fuera del rango [{result.old_value}])\n'
            f'Motivo: {change_reason}\n'
            f'Solicitado por: {changed_by}'
        )
```

---

## 5. UI — PANEL DE CONFIGURACIÓN (Next.js)

### 5.1 Visualización de guardrails en la pantalla de Configuración

Modificar el componente de Configuración para mostrar los rangos y el valor actual de cada parámetro como un slider dentro de los bounds:

```
PARÁMETROS DE RIESGO
══════════════════════════════════════════════════════════════

RR Mínimo — Bajo Riesgo
  [────────●────────────────] 2.0
  Min: 1.5                    Max: 4.0
  Default v3: 2.0 | Estado: ✅ en bounds

RR Mínimo — Riesgo Medio
  [──────────────●──────────] 2.5
  Min: 1.5                    Max: 4.0
  Default v3: 2.5 | Estado: ✅ en bounds

ATR Multiplier — Riesgo Medio
  [──────────●──────────────] 2.0
  Min: 1.0                    Max: 3.5
  Default v3: 2.0 | Estado: ✅ en bounds

══════════════════════════════════════════════════════════════
[📥 Exportar configuración actual]  [↺ Restaurar defaults v3]
```

**Comportamiento del slider:**
- Dentro del rango verde: el cambio se aplica inmediatamente tras validar EV > 0
- Intento de salir del rango: el slider rebota al límite y muestra alerta
- Badge `✅ en bounds` / `⚠️ fuera de bounds` por parámetro

### 5.2 Historial de cambios en el panel

```
HISTORIAL DE CAMBIOS (últimos 10)
═════════════════════════════════════════════════════════════
Fecha          │ Parámetro              │ Antes │ Después │ EV    │ Estado
───────────────┼────────────────────────┼───────┼─────────┼───────┼────────
18 Mar 09:15   │ rr_min_riesgo_medio    │  2.5  │   2.2   │ +0.31 │ ✅ OK
18 Mar 08:45   │ rr_min_riesgo_medio    │  2.5  │   2.0   │ +0.12 │ ❌ Sin EV backtest
17 Mar 15:30   │ atr_mult_bajo_riesgo   │  1.5  │   1.3   │ +0.42 │ ✅ OK
```

---

## 6. NOTIFICACIONES TELEGRAM — ALERTAS DE GUARDRAIL

```python
TELEGRAM_GUARDRAIL_EVENTS = {
    'outside_bounds': (
        '⚠️ APROBACIÓN REQUERIDA — Parámetro fuera de guardrails\n'
        'Parámetro: {parameter_name}\n'
        'Valor actual: {old_value}\n'
        'Valor propuesto: {new_value}\n'
        'Rango permitido: [{min_value}, {max_value}]\n'
        'Solicitado por: {changed_by}\n'
        'Motivo: {change_reason}\n\n'
        'Responder APROBAR o RECHAZAR'
    ),
    'ev_negative': (
        '📉 CAMBIO RECHAZADO — Esperanza matemática negativa\n'
        'Parámetro: {parameter_name}\n'
        'Valor propuesto: {new_value}\n'
        'EV calculado: {ev:.4f} (debe ser > 0)\n'
        'Win rate backtest: {win_rate:.1%}\n'
        'RR promedio: {avg_rr:.2f}\n'
        'Trades en muestra: {total_trades}'
    ),
    'change_accepted': (
        '✅ PARÁMETRO ACTUALIZADO\n'
        '{parameter_name}: {old_value} → {new_value}\n'
        'EV: {ev:.4f} | Por: {changed_by}'
    ),
}
```

---

## 7. TABLA DE ESPERANZA MATEMÁTICA DE REFERENCIA

Esta tabla permite a Antigravity saber rápidamente si un par (win_rate, rr_min) es rentable antes de proponer un cambio:

| Win Rate \ RR | 1.5 | 2.0 | 2.5 | 3.0 |
|--------------|-----|-----|-----|-----|
| **40%**      | -0.10 | +0.20 | +0.40 | +0.60 |
| **45%**      | +0.12 | +0.35 | +0.57 | +0.80 |
| **50%**      | +0.25 | +0.50 | +0.75 | +1.00 |
| **55%**      | +0.37 | +0.65 | +0.92 | +1.20 |
| **60%**      | +0.50 | +0.80 | +1.10 | +1.40 |

**Valores en verde (> 0):** el sistema es matemáticamente rentable a largo plazo.

Ejemplo de uso: si el backtest muestra win_rate=45% con rr_min=2.0, el EV es +0.35. Eso es aceptable. Si win_rate=40% con rr_min=1.5, el EV es -0.10. Ese cambio se rechaza automáticamente.

---

## 8. ENTREGABLES

| # | Archivo | Descripción |
|---|---------|-------------|
| 1 | `app/core/parameter_guard.py` | Módulo de validación (código de Sección 3) |
| 2 | `migration_013_parameter_bounds.sql` | SQL de Secciones 2.1 y 2.2 |
| 3 | Modificar `scheduler.py` | Usar `get_active_params()` en lugar de dict hardcodeado |
| 4 | Modificar `backtester.py` | Usar `get_active_params()` y `validate_parameter_change()` |
| 5 | Modificar panel de Configuración | Sliders con bounds visuales (Sección 5.1) |
| 6 | Agregar historial de cambios en panel | Tabla de Sección 5.2 |

---

## 9. CRITERIOS DE ACEPTACIÓN

- [ ] `parameter_bounds` tiene los 20 parámetros del seed con valores del v3
- [ ] `parameter_changes_log` registra cada intento de cambio (aceptado o rechazado)
- [ ] El scheduler lee parámetros desde Supabase, no desde dict hardcodeado
- [ ] Un cambio dentro del rango sin backtest: se acepta con warning en logs
- [ ] Un cambio dentro del rango con EV negativo: se rechaza automáticamente
- [ ] Un cambio fuera del rango: se rechaza y se envía Telegram con alerta
- [ ] El panel muestra sliders con min/max visibles para cada parámetro
- [ ] El historial de cambios es visible en el panel de Configuración
- [ ] `rr_min_riesgo_medio` = 2.5 (no 2.0) como confirma el documento v3

---

*Documento de guardrails — eTrade v3 — Antigravity Dev Team — Marzo 2026*
