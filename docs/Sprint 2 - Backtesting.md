# 🚀 SPRINT 2 — Backtesting + Dashboard de Performance
## Proyecto: eTrade | Destino: Antigravity Dev Team
**Stack:** Python · Next.js · React · Supabase
**Fecha:** Marzo 2026
**Contexto:** Sprint 1 completado. Paper trading activo en Frankfurt (Render).
4 símbolos corriendo: BTCUSDT, ETHUSDT, SOLUSDT, ADAUSDT.
paper_trades = 0 registros (sistema nuevo, sin señales aún).
El backtesting es urgente para validar las reglas con datos históricos.

---

## PRIORIDAD DE ENTREGABLES

```
FASE 1 (hacer primero):
  1. Backtesting module (Python)
  2. Ejecutar backtest sobre datos históricos
  3. Poblar paper_trades con resultados del backtest

FASE 2 (después de tener datos):
  4. Dashboard de performance por regla (Next.js/React)
  5. Walk-forward testing
  6. Rule Engine version control con performance
  7. Modo Vinculante IA de velas
  8. Slippage tracking dashboard
```

---

## ENTREGABLE 1 — BACKTESTING MODULE (Python)

### 1.1 Descripción

El backtesting corre el pipeline completo de eTrade sobre datos
históricos de Binance (OHLCV ya almacenados en market_candles
o descargados fresh). Simula exactamente la misma lógica que
el scheduler.py pero sobre datos del pasado, registrando cada
trade simulado en paper_trades con todos los campos requeridos
para el dashboard de performance.

### 1.2 Archivo: `app/analysis/backtester.py`

```python
"""
Backtester de eTrade Sprint 2.

Corre el pipeline completo sobre datos históricos:
  1. Descargar OHLCV histórico de Binance (hasta 1000 velas por TF)
  2. Calcular todos los indicadores (Fibonacci BB, ADX, EMA phases)
  3. Evaluar el Rule Engine en cada vela cerrada (misma lógica del scheduler)
  4. Simular entradas y salidas según las reglas de gestión de posición
  5. Registrar cada trade en paper_trades con campo mode='backtest'

IMPORTANTE:
  - Usar EXACTAMENTE la misma lógica del scheduler.py
    No reimplementar indicadores. Importar las mismas funciones.
  - El backtest opera sobre barras cerradas (no la última vela en formación)
  - Simular fill al precio de cierre de la vela de la señal
  - Respetar las mismas reglas de SL, TP parcial y TP total
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional
import pandas as pd

# Importar los mismos módulos del pipeline real
from app.analysis.indicators import (
    fibonacci_bollinger,
    calculate_emas,
    calculate_adx,
    classify_ema20_phase,
    detect_volume_signals,
    detect_reversal_candles,
    calculate_macd_4c,
)
from app.analysis.market_regime import classify_market_risk
from app.analysis.rule_engine import evaluate_rules
from app.providers.binance_provider import BinanceCryptoProvider
from app.utils.supabase_client import get_supabase
from app.utils.logger import log_info, log_warning, log_error

MODULE = "BACKTESTER"


async def run_backtest(
    symbol: str,
    timeframe: str = "15m",
    limit: int = 500,          # número de velas históricas a analizar
    start_from_bar: int = 200, # empezar desde la barra 200 (warm-up completado)
    mode: str = "backtest"
) -> dict:
    """
    Corre el backtest completo para un símbolo y timeframe.

    Args:
        symbol:        'BTCUSDT', 'ETHUSDT', etc.
        timeframe:     '15m', '4h', '1d'
        limit:         cuántas velas descargar (max 1000 para Binance)
        start_from_bar: barra desde donde empezar a evaluar señales
                        (primeras 200 barras son warm-up de indicadores)
        mode:          'backtest' (para distinguir de paper trading)

    Returns:
        {
          'symbol': str,
          'timeframe': str,
          'total_bars_analyzed': int,
          'total_trades': int,
          'winning_trades': int,
          'losing_trades': int,
          'win_rate_pct': float,
          'total_pnl_usd': float,
          'avg_rr_real': float,
          'rules_triggered': dict,  # {rule_code: count}
          'trades': list            # lista de trades para insertar en paper_trades
        }
    """
    log_info(MODULE, f"Iniciando backtest {symbol} {timeframe} ({limit} velas)")

    provider = BinanceCryptoProvider(market='futures')

    # 1. Descargar datos históricos
    df_15m = await provider.get_ohlcv(symbol, timeframe, limit=limit)
    df_4h  = await provider.get_ohlcv(symbol, '4h',  limit=200)
    df_1d  = await provider.get_ohlcv(symbol, '1d',  limit=200)

    if df_15m is None or len(df_15m) < start_from_bar:
        log_warning(MODULE, f"Datos insuficientes para {symbol}")
        return {'error': 'Datos insuficientes'}

    # 2. Pre-calcular indicadores para 4h y 1d (basis multi-TF)
    df_4h = fibonacci_bollinger(df_4h)
    df_1d = fibonacci_bollinger(df_1d)

    # 3. Calcular indicadores completos sobre datos de 15m
    df = fibonacci_bollinger(df_15m)
    df = calculate_emas(df)
    df = calculate_adx(df)
    df = classify_ema20_phase(df)
    df = detect_volume_signals(df)
    df = detect_reversal_candles(df)
    df = calculate_macd_4c(df)

    # 4. Simular trading barra por barra
    trades = []
    open_position = None
    rules_triggered = {}

    for i in range(start_from_bar, len(df)):
        bar = df.iloc[:i+1]  # datos disponibles hasta esta barra
        last = bar.iloc[-1]
        current_price = float(last['close'])

        # Obtener basis de 4h y 1d para la barra actual
        basis_4h = _get_basis_for_bar(df_4h, last.name)
        basis_1d = _get_basis_for_bar(df_1d, last.name)

        # Calcular régimen de mercado
        regime = classify_market_risk(bar)

        # Evaluar cierre de posición abierta
        if open_position:
            close_result = _evaluate_position_close(
                open_position, last, current_price
            )
            if close_result['should_close']:
                trade = _close_position(
                    open_position, close_result, last, symbol, mode
                )
                trades.append(trade)
                open_position = None

        # Evaluar apertura de nueva posición (solo si no hay posición abierta)
        if not open_position:
            signal = evaluate_rules(
                bar=last,
                regime=regime,
                basis_4h=basis_4h,
                basis_1d=basis_1d,
                open_position=None
            )

            if signal and signal.get('rule_triggered'):
                rule_code = signal.get('rule_evaluated', 'unknown')
                rules_triggered[rule_code] = rules_triggered.get(rule_code, 0) + 1

                open_position = _open_position(
                    signal, last, current_price, symbol, regime, mode
                )

    # Cerrar posición abierta al final del backtest
    if open_position:
        last = df.iloc[-1]
        trade = _close_position(
            open_position,
            {'should_close': True, 'reason': 'end_of_backtest'},
            last, symbol, mode
        )
        trades.append(trade)

    # 5. Calcular métricas de performance
    results = _calculate_performance_metrics(trades, symbol, timeframe)
    results['rules_triggered'] = rules_triggered
    results['trades'] = trades

    log_info(MODULE, f"Backtest completado: {len(trades)} trades, "
             f"win rate: {results.get('win_rate_pct', 0):.1f}%")

    return results


def _get_basis_for_bar(df_higher_tf: pd.DataFrame, timestamp) -> Optional[float]:
    """Obtiene el basis VWMA del timeframe superior para un timestamp dado."""
    if df_higher_tf is None or 'basis' not in df_higher_tf.columns:
        return None
    # Obtener la última vela del TF superior que haya cerrado antes del timestamp
    mask = df_higher_tf.index <= timestamp
    if not mask.any():
        return None
    return float(df_higher_tf.loc[mask, 'basis'].iloc[-1])


def _open_position(signal, bar, price, symbol, regime, mode) -> dict:
    """Crea una posición simulada."""
    atr = float(bar.get('atr', 0))
    atr_mult = regime['active_params'].get('atr_mult', 2.0)
    side = 'long' if signal.get('direction') == 'long' else 'short'

    sl_price = (
        price - (atr * atr_mult) if side == 'long'
        else price + (atr * atr_mult)
    )
    # TP desde bandas Fibonacci
    tp_partial = float(bar.get('upper_5' if side == 'long' else 'lower_5', price))
    tp_full    = float(bar.get('upper_6' if side == 'long' else 'lower_6', price))

    return {
        'symbol':        symbol,
        'side':          side,
        'entry_price':   price,
        'entry_time':    bar.name,
        'sl_price':      sl_price,
        'tp_partial':    tp_partial,
        'tp_full':       tp_full,
        'rule_code':     signal.get('rule_evaluated', 'unknown'),
        'regime':        regime['category'],
        'risk_score':    regime['risk_score'],
        'ema20_phase':   str(bar.get('ema20_phase', '')),
        'adx_value':     float(bar.get('adx', 0)),
        'fibonacci_zone': int(bar.get('fibonacci_zone', 0)),
        'mode':          mode,
    }


def _evaluate_position_close(position, bar, current_price) -> dict:
    """Evalúa si la posición debe cerrarse en esta barra."""
    side = position['side']

    # SL hit
    if side == 'long' and current_price <= position['sl_price']:
        return {'should_close': True, 'reason': 'sl', 'exit_price': position['sl_price']}
    if side == 'short' and current_price >= position['sl_price']:
        return {'should_close': True, 'reason': 'sl', 'exit_price': position['sl_price']}

    # TP total
    if side == 'long' and current_price >= position['tp_full']:
        # Verificar confirmación de volumen y vela
        vol_ok = bool(bar.get('vol_decreasing', False))
        candle_ok = (
            bool(bar.get('is_gravestone', False)) or
            bool(bar.get('high_lower_than_prev', False)) or
            (bool(bar.get('is_red_candle', False)) and current_price >= position['tp_full'])
        )
        # Modo defensivo (EMA50 < EMA200): cerrar sin esperar confirmación
        defensive = float(bar.get('ema4', 0)) < float(bar.get('ema5', 0))
        if vol_ok and candle_ok or defensive:
            return {'should_close': True, 'reason': 'tp_full', 'exit_price': current_price}

    if side == 'short' and current_price <= position['tp_full']:
        vol_ok = bool(bar.get('vol_increasing', False))
        candle_ok = (
            bool(bar.get('is_dragonfly', False)) or
            bool(bar.get('low_higher_than_prev', False)) or
            (bool(bar.get('is_green_candle', False)) and current_price <= position['tp_full'])
        )
        defensive = float(bar.get('ema4', 0)) < float(bar.get('ema5', 0))
        if vol_ok and candle_ok or defensive:
            return {'should_close': True, 'reason': 'tp_full', 'exit_price': current_price}

    return {'should_close': False}


def _close_position(position, close_result, bar, symbol, mode) -> dict:
    """Genera el registro de trade para insertar en paper_trades."""
    entry  = position['entry_price']
    exit_p = close_result.get('exit_price', float(bar['close']))
    side   = position['side']

    if side == 'long':
        pnl_pct = (exit_p - entry) / entry * 100
    else:
        pnl_pct = (entry - exit_p) / entry * 100

    # Capital simulado: usar distribución T1 (20% de $90 = $18)
    capital_t1 = 18.0
    pnl_usd    = capital_t1 * (pnl_pct / 100)

    return {
        'symbol':              symbol,
        'side':                side,
        'entry_price':         entry,
        'exit_price':          exit_p,
        'sl_price':            position['sl_price'],
        'tp_price':            position['tp_full'],
        'close_reason':        close_result.get('reason', 'unknown'),
        'pnl_pct':             round(pnl_pct, 4),
        'pnl_usd':             round(pnl_usd, 4),
        'rule_code':           position.get('rule_code', 'unknown'),
        'regime':              position.get('regime', 'unknown'),
        'risk_score':          position.get('risk_score', 0),
        'ema20_phase':         position.get('ema20_phase', ''),
        'adx_value':           position.get('adx_value', 0),
        'fibonacci_zone_entry': position.get('fibonacci_zone', 0),
        'opened_at':           str(position.get('entry_time', '')),
        'closed_at':           str(bar.name),
        'mode':                mode,   # 'backtest'
        'market_type':         'futures',
        'leverage':            5,
    }


def _calculate_performance_metrics(trades: list, symbol: str, timeframe: str) -> dict:
    """Calcula métricas agregadas del backtest."""
    if not trades:
        return {
            'symbol': symbol, 'timeframe': timeframe,
            'total_trades': 0, 'winning_trades': 0,
            'losing_trades': 0, 'win_rate_pct': 0.0,
            'total_pnl_usd': 0.0, 'avg_rr_real': 0.0,
        }

    winning = [t for t in trades if t['pnl_pct'] > 0]
    losing  = [t for t in trades if t['pnl_pct'] <= 0]

    total_pnl = sum(t['pnl_usd'] for t in trades)
    avg_rr    = (
        sum(t['pnl_pct'] for t in winning) / len(winning)
        if winning else 0
    )

    return {
        'symbol':          symbol,
        'timeframe':       timeframe,
        'total_trades':    len(trades),
        'winning_trades':  len(winning),
        'losing_trades':   len(losing),
        'win_rate_pct':    round(len(winning) / len(trades) * 100, 1),
        'total_pnl_usd':   round(total_pnl, 2),
        'avg_rr_real':     round(avg_rr, 2),
    }


async def save_backtest_to_supabase(results: dict) -> bool:
    """
    Inserta los trades del backtest en paper_trades
    y el resumen en backtest_runs.
    """
    sb = get_supabase()
    trades = results.pop('trades', [])

    # 1. Guardar resumen en backtest_runs
    try:
        sb.table('backtest_runs').insert({
            'symbol':         results.get('symbol'),
            'timeframe':      results.get('timeframe'),
            'total_trades':   results.get('total_trades'),
            'winning_trades': results.get('winning_trades'),
            'losing_trades':  results.get('losing_trades'),
            'win_rate_pct':   results.get('win_rate_pct'),
            'total_pnl_usd':  results.get('total_pnl_usd'),
            'avg_rr_real':    results.get('avg_rr_real'),
            'rules_triggered': results.get('rules_triggered'),
            'ran_at':         datetime.now(timezone.utc).isoformat(),
            'mode':           'backtest',
        }).execute()
    except Exception as e:
        log_error(MODULE, f"Error guardando backtest_runs: {e}")

    # 2. Insertar trades en paper_trades en lotes de 100
    if trades:
        batch_size = 100
        for i in range(0, len(trades), batch_size):
            batch = trades[i:i+batch_size]
            try:
                sb.table('paper_trades').insert(batch).execute()
                log_info(MODULE, f"Insertadas {len(batch)} trades en paper_trades")
            except Exception as e:
                log_error(MODULE, f"Error insertando batch: {e}")
                return False

    return True
```

---

### 1.3 Script de ejecución: `run_backtest.py`

Crear en la raíz del backend:

```python
"""
Script para ejecutar el backtesting manualmente.
Uso: python run_backtest.py
"""
import asyncio
from app.analysis.backtester import run_backtest, save_backtest_to_supabase

SYMBOLS    = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT']
TIMEFRAMES = ['15m']
LIMIT      = 500  # velas históricas por símbolo

async def main():
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            print(f"\n{'='*50}")
            print(f"Backtesting {symbol} {tf}...")
            print(f"{'='*50}")

            results = await run_backtest(
                symbol=symbol,
                timeframe=tf,
                limit=LIMIT
            )

            if 'error' in results:
                print(f"ERROR: {results['error']}")
                continue

            print(f"Total trades:   {results['total_trades']}")
            print(f"Win rate:       {results['win_rate_pct']}%")
            print(f"P&L total:      ${results['total_pnl_usd']}")
            print(f"RR promedio:    {results['avg_rr_real']}")
            print(f"Reglas activas: {results['rules_triggered']}")

            await save_backtest_to_supabase(results)
            print(f"✅ Guardado en Supabase")

if __name__ == '__main__':
    asyncio.run(main())
```

---

## ENTREGABLE 2 — TABLA backtest_runs (verificar columnas)

Verificar que la tabla `backtest_runs` existente tiene estas columnas.
Agregar las que falten:

```sql
ALTER TABLE backtest_runs
  ADD COLUMN IF NOT EXISTS symbol          VARCHAR(20),
  ADD COLUMN IF NOT EXISTS timeframe       VARCHAR(5),
  ADD COLUMN IF NOT EXISTS total_trades    INT,
  ADD COLUMN IF NOT EXISTS winning_trades  INT,
  ADD COLUMN IF NOT EXISTS losing_trades   INT,
  ADD COLUMN IF NOT EXISTS win_rate_pct    NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS total_pnl_usd   NUMERIC(10,4),
  ADD COLUMN IF NOT EXISTS avg_rr_real     NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS rules_triggered JSONB,
  ADD COLUMN IF NOT EXISTS ran_at          TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS mode            VARCHAR(20) DEFAULT 'backtest',
  ADD COLUMN IF NOT EXISTS parameters      JSONB;
  -- parameters: {limit, start_from_bar, capital_t1, etc.}
```

---

## ENTREGABLE 3 — DASHBOARD DE PERFORMANCE (Next.js/React)

### 3.1 Página: `/pages/performance.tsx`

Mostrar después de tener datos en `paper_trades` con `mode='backtest'`.

**Secciones del dashboard:**

```
DASHBOARD DE PERFORMANCE — eTrade
══════════════════════════════════════════════════════════

FILTROS:
  Símbolo: [BTCUSDT ▼] [ETHUSDT ▼] [SOLUSDT ▼] [ADAUSDT ▼] [Todos]
  Modo:    [Backtest] [Paper Trading] [Todos]
  Período: [Último mes ▼]

──────────────────────────────────────────────────────────
MÉTRICAS GENERALES
  Total trades:  XX    Win rate: XX%    P&L total: $XX.XX
  RR promedio:   X.XX  Avg hold: XX velas
──────────────────────────────────────────────────────────
PERFORMANCE POR REGLA
  ┌──────┬───────┬────────┬──────────┬───────────┬──────────┐
  │Regla │Trades │Win Rate│P&L ($)   │RR Prom    │Último uso│
  ├──────┼───────┼────────┼──────────┼───────────┼──────────┤
  │Aa13  │  12   │  75%   │  +$8.40  │   2.8     │ hace 2h  │
  │Aa22  │   8   │  62%   │  +$3.20  │   2.1     │ hace 5h  │
  │Bb12  │   5   │  80%   │  +$6.10  │   3.2     │ hace 1d  │
  │Bb22  │   3   │  33%   │  -$1.80  │   1.4 ⚠️  │ hace 2d  │
  └──────┴───────┴────────┴──────────┴───────────┴──────────┘
  ⚠️ = RR promedio por debajo del mínimo configurado
──────────────────────────────────────────────────────────
PERFORMANCE POR RÉGIMEN
  🔴 Alto riesgo:  X trades  XX% win rate
  🟡 Riesgo medio: X trades  XX% win rate
  🟢 Bajo riesgo:  X trades  XX% win rate
──────────────────────────────────────────────────────────
ÚLTIMOS TRADES
  Symbol │ Side  │ Rule │ Entry   │ Exit    │ P&L    │ Razón
  BTCUSDT│ LONG  │ Aa22 │ $84,200 │ $86,100 │ +$2.1  │ tp_full
  ETHUSDT│ SHORT │ Bb12 │ $3,240  │ $3,180  │ +$1.4  │ tp_partial
══════════════════════════════════════════════════════════
```

### 3.2 Query principal del dashboard

```sql
SELECT
  rule_code,
  COUNT(*) as total_trades,
  SUM(CASE WHEN total_pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
  ROUND(AVG(total_pnl_pct), 2) as avg_pnl_pct,
  ROUND(SUM(total_pnl_usd), 2) as total_pnl_usd,
  ROUND(
    SUM(CASE WHEN total_pnl_pct > 0 THEN 1 ELSE 0 END)::numeric
    / COUNT(*) * 100, 1
  ) as win_rate_pct,
  MAX(closed_at) as ultimo_trade
FROM paper_trades
WHERE mode IN ('backtest', 'paper')
GROUP BY rule_code
ORDER BY total_pnl_usd DESC;
```

---

## ENTREGABLE 4 — WALK-FORWARD TESTING

Después de tener el backtesting funcionando.

```python
async def run_walk_forward(
    symbol: str,
    total_bars: int = 500,
    train_pct: float = 0.70,
    test_pct:  float = 0.30
):
    """
    Walk-forward testing:
      - 70% primeras barras: in-sample (calibración)
      - 30% últimas barras:  out-of-sample (validación)

    Si el win rate out-of-sample cae más de 15 puntos
    respecto al in-sample, hay overfitting en los parámetros.
    """
    split = int(total_bars * train_pct)

    results_train = await run_backtest(symbol, limit=split)
    results_test  = await run_backtest(
        symbol, limit=total_bars, start_from_bar=split
    )

    degradation = (
        results_train['win_rate_pct'] - results_test['win_rate_pct']
    )

    return {
        'in_sample_win_rate':  results_train['win_rate_pct'],
        'out_sample_win_rate': results_test['win_rate_pct'],
        'degradation_pct':     round(degradation, 1),
        'overfitting_risk':    'HIGH' if degradation > 15 else
                               'MEDIUM' if degradation > 8 else 'LOW',
    }
```

---

## CRITERIOS DE ACEPTACIÓN SPRINT 2

```
BACKTESTING:
  [ ] run_backtest.py ejecuta sin errores para los 4 símbolos
  [ ] paper_trades tiene registros con mode='backtest' después de correr
  [ ] backtest_runs tiene el resumen por símbolo
  [ ] Los trades de backtest incluyen rule_code, regime, ema20_phase

DASHBOARD:
  [ ] Página /performance carga sin errores
  [ ] Tabla de performance por regla muestra win rate y P&L
  [ ] Filtros por símbolo y modo funcionan
  [ ] Se actualiza con Supabase Realtime cuando llegan nuevos trades

WALK-FORWARD:
  [ ] run_walk_forward ejecuta para BTCUSDT
  [ ] Reporta degradation_pct entre in-sample y out-of-sample
  [ ] Resultado guardado en backtest_runs con campo overfitting_risk
```

---

## ORDEN DE EJECUCIÓN PARA ANTIGRAVITY

```
DÍA 1:
  1. Implementar backtester.py
  2. Verificar que importa correctamente los módulos del pipeline
  3. Correr run_backtest.py localmente con BTCUSDT
  4. Verificar que paper_trades se puebla correctamente

DÍA 2:
  5. Correr backtest para los 4 símbolos
  6. Implementar dashboard /performance en Next.js
  7. Verificar que las métricas por regla se calculan correctamente

DÍA 3:
  8. Implementar walk-forward testing
  9. Implementar Rule Engine version control con performance

DESPUÉS:
  10. Modo Vinculante IA de velas (requiere validar paper trading primero)
  11. Slippage tracking dashboard
```

---

## VERIFICACIÓN INICIAL (antes de empezar)

Ejecutar en Supabase para confirmar el estado actual:

```sql
-- Confirmar que paper_trades está vacío (normal, sistema nuevo)
SELECT COUNT(*), mode FROM paper_trades GROUP BY mode;

-- Confirmar que backtest_runs existe
SELECT COUNT(*) FROM backtest_runs;

-- Confirmar columnas de paper_trades para el backtesting
SELECT column_name FROM information_schema.columns
WHERE table_name = 'paper_trades'
  AND column_name IN (
    'rule_code', 'regime', 'ema20_phase', 'adx_value',
    'total_pnl_usd', 'total_pnl_pct', 'close_reason', 'mode'
  );
-- Debe retornar 8 columnas. Si faltan, aplicar ALTER TABLE.
```

---

*Sprint 2 — eTrade · Antigravity Dev Team — Marzo 2026*
