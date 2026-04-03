# 🚀 ENGINEERING BRIEF v4 — eTrade: Plataforma de Trading Algorítmico Multi-Símbolo
## Proyecto: eTrade | Destino: Antigravity Dev Team
**Stack:** Python · Next.js · React · Supabase
**Fecha:** Marzo 2026 | **Versión:** 4.0 — Documento maestro Sprint 1
**Solicitado por:** Jhon (CEO)
**Cambio principal v4:** Estrategia de base de datos mínima — Memory-First Architecture

---

## ÍNDICE

1.  Objetivo y Alcance
2.  Principio Rector — Memory-First, DB-Last
3.  Arquitectura de Tres Velocidades
4.  Capa de Análisis Técnico
5.  Régimen Dinámico de Mercado
6.  Rule Engine — Motor de Reglas
7.  Fase 4 — Decisión de Entrada LONG / SHORT
8.  Gestión de Capital y Sizing
9.  Gestión de Posición
10. Protecciones de Riesgo
11. Infraestructura y DataProvider
12. Estrategia de Base de Datos — Qué se graba y qué no
13. Frontend — Next.js / React
14. Notificaciones Telegram
15. Paper Trading Mode
16. Entregables y Criterios de Aceptación Sprint 1
17. Hoja de Ruta Sprints 2 y 3

---

## 1. OBJETIVO Y ALCANCE

### 1.1 Descripción del sistema

eTrade es una plataforma de trading algorítmico multi-símbolo que opera en mercados de
**Crypto SPOT y Crypto FUTURES** (Binance). Combina análisis técnico clásico (Fibonacci
Bollinger Bands, ADX, EMAs), gestión dinámica de riesgo por régimen de mercado, un motor
de reglas editable, e interpretación contextual de velas mediante IA (Anthropic API).

### 1.2 Alcance Sprint 1

- **Mercados:** Crypto SPOT + Crypto FUTURES (Binance)
- **Símbolos iniciales:** BTC/USDT, ETH/USDT, SOL/USDT, ADA/USDT
- **Timeframes:** 5m (alertas), 15m (señales), 30m, 45m, 4h, 1d, 1w
- **Modo operativo inicial:** Paper Trading con precios reales de Binance
- **Toggle en login:** Paper Trading / Modo Real

### 1.3 Fuera de scope Sprint 1

- Forex, Bolsa, Opciones → Sprint 3+
- Backtesting module → Sprint 2
- Walk-forward testing → Sprint 2
- Modo Vinculante de IA candlestick → Sprint 2

---

## 2. PRINCIPIO RECTOR — MEMORY-FIRST, DB-LAST ⭐ NUEVO EN v4

### 2.1 La regla de oro

> **Ningún dato se graba en Supabase a menos que sea imposible reconstruirlo
> si el worker se reinicia.**

Todo lo que se puede recalcular desde Binance en el próximo ciclo de 15m
**vive solo en memoria**. Supabase guarda únicamente **estado de negocio**
(posiciones, trades, configuración, reglas) y **eventos auditables** (señales,
cambios de régimen, errores críticos).

### 2.2 Clasificación de datos en tres capas

```
┌─────────────────────────────────────────────────────────────────┐
│                  CLASIFICACIÓN DE DATOS — v4                    │
├───────────────┬──────────────────────────┬──────────────────────┤
│  CAPA         │  DÓNDE VIVE              │  QUÉ CONTIENE        │
├───────────────┼──────────────────────────┼──────────────────────┤
│  🔴 HOT       │  Python dict en memoria  │  OHLCV raw           │
│  (volátil)    │  Se pierde al reiniciar  │  Indicadores técnicos│
│               │  Se reconstruye de       │  (EMA, ADX, Fib BB)  │
│               │  Binance en warm-up      │  Precios en tiempo   │
│               │                          │  real del WebSocket  │
│               │                          │  Régimen actual      │
│               │                          │  Estado de señales   │
├───────────────┼──────────────────────────┼──────────────────────┤
│  🟡 WARM      │  Supabase — filas        │  Posiciones abiertas │
│  (estado      │  actualizadas,           │  Órdenes pendientes  │
│  operativo)   │  no acumuladas           │  Cooldowns activos   │
│               │  1 fila por símbolo,     │  Estado circuit      │
│               │  se sobreescribe (upsert)│  breaker             │
│               │                          │  P&L del día         │
├───────────────┼──────────────────────────┼──────────────────────┤
│  🟢 COLD      │  Supabase — filas        │  Trades cerrados     │
│  (histórico   │  append-only,            │  Configuración       │
│  auditable)   │  nunca se borran*        │  Reglas del Engine   │
│               │  (*excepto cleanup       │  Historial régimen   │
│               │  programado)             │  Logs de señales     │
│               │                          │  Reconciliaciones    │
└───────────────┴──────────────────────────┴──────────────────────┘
```

### 2.3 Estimación de escrituras a Supabase por ciclo

Con 4 símbolos activos, el sistema genera las siguientes escrituras:

```
EVENTO                        FRECUENCIA        FILAS/DÍA   TIPO
────────────────────────────────────────────────────────────────
Upsert posición abierta       Solo si cambia    0 - 4       WARM
Upsert estado régimen         Cada 15m × 4      384         WARM (sobreescribe)
Upsert cooldown               Solo tras SL/TP   0 - 8       WARM (sobreescribe)
Insert trade cerrado          Solo al cerrar    0 - 20      COLD
Insert señal detectada        Solo cuando hay   0 - 30      COLD
Insert cambio de régimen      Solo si cambia    0 - 20      COLD
Insert log reconciliación     Cada 45m          128         COLD
────────────────────────────────────────────────────────────────
TOTAL ESTIMADO (día normal):  < 600 filas/día
TOTAL SIN ESTA ESTRATEGIA:    > 50,000 filas/día (si se guardara OHLCV)
────────────────────────────────────────────────────────────────
AHORRO: 98% menos escrituras vs guardar OHLCV en DB
```

### 2.4 Reconexión y warm-up (el worker se reinicia)

Al reiniciarse el worker Python, la memoria HOT se pierde. El procedimiento:

```python
async def worker_startup(symbols: list, provider: DataProvider):
    """
    Ejecutar al iniciar el worker (en Render, al desplegar, o tras caída).

    1. Leer estado WARM de Supabase (posiciones, cooldowns, circuit breaker)
       → Estos datos sobreviven al reinicio porque están en Supabase
    2. Descargar histórico de Binance para reconstruir indicadores en memoria
       → NO se leen de Supabase porque nunca se guardaron ahí
    3. Suscribir WebSocket streams
    4. Reanudar operación normal

    Tiempo estimado de warm-up: 15-30 segundos para 4 símbolos.
    """
    # Paso 1: Recuperar estado de negocio de Supabase
    state = await supabase.table('bot_state').select('*').execute()
    # → posiciones abiertas, cooldowns, circuit breaker, etc.

    # Paso 2: Reconstruir indicadores en memoria desde Binance
    for symbol in symbols:
        for timeframe in TIMEFRAMES:
            df = await provider.get_ohlcv(symbol, timeframe, limit=500)
            MEMORY_STORE[symbol][timeframe] = calculate_all_indicators(df)

    # Paso 3: WebSocket
    await ws_manager.connect(symbols)

    log("Worker iniciado — estado recuperado de Supabase, indicadores reconstruidos de Binance")
```

---

## 3. ARQUITECTURA DE TRES VELOCIDADES

**Regla fundamental:**
- Señales de **ENTRADA** → solo en ciclo 15m
- Alertas de **CIERRE** → ciclo 5m + WebSocket
- **DB writes** → solo en cambios de estado, nunca en cada tick

```
┌─────────────────────────────────────────────────────────────────┐
│               ARQUITECTURA DE TRES VELOCIDADES v4               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  VELOCIDAD 1 — WebSocket (tiempo real, continuo)                │
│  Datos:   precio actual → MEMORIA solamente                     │
│  DB write: NUNCA (solo alerta a Telegram si emergencia)         │
│  Acción:  comparar ATR en memoria → disparar emergencia         │
│                                                                  │
│  VELOCIDAD 2A — Ciclo 5 minutos                                 │
│  Datos:   recalcular indicadores críticos → MEMORIA             │
│  DB write: SOLO si posición cambia (break-even, SL update)      │
│  Acciones:                                                       │
│    → Re-evaluar liquidation price vs precio actual              │
│    → Re-evaluar break-even (si se cumple → upsert posición)     │
│    → Leer funding rate de Binance → MEMORIA                     │
│    → Verificar órdenes parcialmente llenadas                    │
│    → Evaluar condición de CIERRE de posición abierta            │
│    → Alerta Telegram si corresponde cierre                      │
│                                                                  │
│  VELOCIDAD 2B — Ciclo 15 minutos (ciclo principal)             │
│  Datos:   vela cerrada → recalcular todo en MEMORIA             │
│  DB write: solo si hay cambio de régimen, señal o posición      │
│  Acciones:                                                       │
│    → Clasificación de régimen (→ upsert si cambia de categoría) │
│    → Cálculo completo de indicadores → MEMORIA                  │
│    → Interpretación IA de velas → MEMORIA + insert log          │
│    → Evaluación Rule Engine → insert señal si hay               │
│    → Decisión de apertura → insert posición si corresponde      │
│    → Reconciliación (cada 3 ciclos = 45m) → insert log          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 Estructura de memoria en Python

```python
from collections import defaultdict
import pandas as pd

# Estructura central en memoria — NUNCA se guarda en Supabase
MEMORY_STORE: dict = defaultdict(lambda: defaultdict(dict))
# Estructura: MEMORY_STORE[symbol][timeframe] = {
#     'df':          pd.DataFrame con OHLCV + todos los indicadores,
#     'last_updated': datetime,
#     'regime':       dict clasificación de mercado actual,
#     'basis_15m':    float,
#     'basis_4h':     float,
#     'basis_1d':     float,
#     'ai_cache':     dict última interpretación IA (evita llamadas repetidas),
#     'ai_cache_bar': int índice de vela cuando se hizo la última llamada IA,
# }

# Estado de negocio — se recupera de Supabase al iniciar
BOT_STATE: dict = {
    'positions':       {},   # {symbol: Position}
    'cooldowns':       {},   # {symbol: cooldown_expiry}
    'circuit_breaker': {'triggered': False, 'daily_pnl': 0.0},
    'emergency':       {},   # {symbol: bool}
    'regime_cache':    {},   # {symbol: último régimen conocido}
}
```

---

## 4. CAPA DE ANÁLISIS TÉCNICO

*Todos los cálculos viven en MEMORIA. Nada de esta sección se escribe en Supabase.*

### 4.1 Fibonacci Bollinger Bands

```python
FIBONACCI_RATIOS = [0.236, 0.382, 0.500, 0.618, 0.764, 1.000]

def fibonacci_bollinger(df: pd.DataFrame,
                         length: int = 200,
                         mult:   float = 3.0,
                         src_col: str = 'hlc3') -> pd.DataFrame:
    """
    CRÍTICO — tres invariantes:
    1. VWMA como basis (NO SMA): sum(price×vol,n) / sum(vol,n)
    2. ddof=0 en std (desviación de POBLACIÓN = PineScript)
    3. src = hlc3 = (high + low + close) / 3

    Resultado: columnas basis, upper_1..6, lower_1..6 añadidas al df.
    El df vive en MEMORY_STORE[symbol][timeframe]['df'].
    """
    df = df.copy()
    if src_col == 'hlc3':
        df['hlc3'] = (df['high'] + df['low'] + df['close']) / 3

    src     = df[src_col]
    typvol  = src * df['volume']
    df['basis'] = (
        typvol.rolling(window=length).sum() /
        df['volume'].rolling(window=length).sum()
    )
    dev = mult * src.rolling(window=length).std(ddof=0)

    for i, ratio in enumerate(FIBONACCI_RATIOS, start=1):
        df[f'upper_{i}'] = df['basis'] + ratio * dev
        df[f'lower_{i}'] = df['basis'] - ratio * dev

    return df


def get_fibonacci_zone(price: float, row: pd.Series) -> int:
    """
    Corrección del bug PineScript donde (nOp <= basis OR nOp > basis)
    siempre cortocircuitaba a 0. En Python se evalúan extremos primero.
    Retorna: -6 ... 0 ... +6
    """
    if price <= row['lower_6']: return -6
    if price <  row['lower_5']: return -5
    if price <  row['lower_4']: return -4
    if price <  row['lower_3']: return -3
    if price <  row['lower_2']: return -2
    if price <  row['lower_1']: return -1
    if price >  row['upper_6']: return  6
    if price >  row['upper_5']: return  5
    if price >  row['upper_4']: return  4
    if price >  row['upper_3']: return  3
    if price >  row['upper_2']: return  2
    if price >  row['upper_1']: return  1
    return 0
```

### 4.2 Basis Multi-Timeframe (15m + 4h + 1d)

```python
def calculate_basis_confluence(symbol: str, price: float, direction: str) -> dict:
    """
    Lee los tres basis desde MEMORY_STORE (ya calculados en el ciclo).
    No hace ninguna consulta a Supabase.

    Confluence score:
      3 TFs alineados → sizing × 1.00
      2 TFs alineados → sizing × 0.85
      1 TF alineado   → sizing × 0.70
    """
    basis_15m = MEMORY_STORE[symbol]['15m']['df']['basis'].iloc[-1]
    basis_4h  = MEMORY_STORE[symbol]['4h']['df']['basis'].iloc[-1]
    basis_1d  = MEMORY_STORE[symbol]['1d']['df']['basis'].iloc[-1]

    score = 0
    check = (lambda b: price > b) if direction == 'long' else (lambda b: price < b)
    for b in [basis_15m, basis_4h, basis_1d]:
        if check(b): score += 1

    return {
        'score':      score,
        'multiplier': {1: 0.70, 2: 0.85, 3: 1.00}[score],
        'basis_15m':  float(basis_15m),
        'basis_4h':   float(basis_4h),
        'basis_1d':   float(basis_1d),
    }
```

### 4.3 MACD 4 Colores (4C)

```python
def calculate_macd_4c(df: pd.DataFrame,
                       fast: int = 12, slow: int = 26) -> pd.DataFrame:
    """
    Tipo:
      1 = MACD > 0 subiendo   (bullish strong)
      2 = MACD > 0 bajando    (bullish weak → Sell signal)
      3 = MACD < 0 bajando    (bearish strong)
      4 = MACD < 0 subiendo   (bearish weak → Buy signal)

    b_macd_buy  = tipo 4 después de 3, 3
    b_macd_sell = tipo 2 después de 1, 1
    """
    df = df.copy()
    df['macd'] = (
        df['close'].ewm(span=fast, adjust=False).mean() -
        df['close'].ewm(span=slow, adjust=False).mean()
    )
    prev = df['macd'].shift(1)
    df['macd_4c'] = np.select(
        [(df['macd'] > 0) & (df['macd'] > prev),
         (df['macd'] > 0) & (df['macd'] <= prev),
         (df['macd'] < 0) & (df['macd'] < prev),
         (df['macd'] < 0) & (df['macd'] >= prev)],
        [1, 2, 3, 4], default=0
    )
    c = df['macd_4c']
    df['macd_buy']  = (c == 4) & (c.shift(1) == 3) & (c.shift(2) == 3)
    df['macd_sell'] = (c == 2) & (c.shift(1) == 1) & (c.shift(2) == 1)
    return df
```

### 4.4 EMAs y Ángulo EMA20 por Percentiles Adaptativos

```python
def calculate_emas(df: pd.DataFrame,
                   v1=3, v2=9, v3=20, v4=50, v5=200) -> pd.DataFrame:
    df = df.copy()
    for i, span in enumerate([v1, v2, v3, v4, v5], start=1):
        df[f'ema{i}'] = df['close'].ewm(span=span, adjust=False).mean()
    return df


def classify_ema20_phase(df: pd.DataFrame,
                          flat_pct:       float = 20.0,
                          peak_pct:       float = 80.0,
                          lookback_window: int  = 100,
                          atr_lookback:   int   = 10) -> pd.DataFrame:
    """
    PERCENTILES ADAPTATIVOS — sin umbrales fijos.
    Funciona para BTC/15m, SOL/4h o cualquier par/TF
    sin intervención manual.

    flat_pct, peak_pct y lookback_window son configurables por régimen.
    """
    df = df.copy()

    # ATR normaliza el ángulo (igual a f_angle del PineScript original)
    df['atr'] = (
        df[['high', 'close']].max(axis=1) -
        df[['low',  'close']].min(axis=1)
    ).rolling(atr_lookback).mean()

    df['ema20_angle'] = np.degrees(
        np.arctan(
            (df['ema3'] - df['ema3'].shift(2)) /
            (df['atr'] * 2 + 1e-10)
        )
    )

    # Percentil rolling — auto-adaptativo al activo/TF
    df['ema20_pct'] = (
        df['ema20_angle'].rolling(lookback_window).rank(pct=True) * 100
    )

    flat_std = df['ema20_angle'].rolling(lookback_window).std()
    is_flat  = df['ema20_angle'].abs() < (flat_std * 0.3)

    peak_5   = df['ema20_angle'].rolling(5).max()
    falling  = (df['ema20_angle'] > 0) & (df['ema20_angle'] < peak_5) & (df['ema20_pct'] >= peak_pct * 0.6)

    phases = [
        'flat',
        'nivel_1_long',  'nivel_2_long',  'nivel_3_long',
        'nivel_1_short', 'nivel_2_short', 'nivel_3_short',
    ]
    conditions = [
        is_flat,
        (~is_flat) & (df['ema20_angle'] > 0) & df['ema20_pct'].between(flat_pct, 50),
        (~is_flat) & (df['ema20_angle'] > 0) & df['ema20_pct'].between(50, peak_pct),
        (~is_flat) & (df['ema20_angle'] > 0) & falling,
        (~is_flat) & (df['ema20_angle'] < 0) & df['ema20_pct'].between(100-flat_pct, 50),
        (~is_flat) & (df['ema20_angle'] < 0) & df['ema20_pct'].between(100-peak_pct, 100-flat_pct),
        (~is_flat) & (df['ema20_angle'] < 0) & falling,
    ]
    df['ema20_phase']       = np.select(conditions, phases, default='flat')
    df['was_flat_recently'] = df['ema20_phase'].shift(1).isin(['flat']) | \
                              df['ema20_phase'].shift(2).isin(['flat']) | \
                              df['ema20_phase'].shift(3).isin(['flat'])
    df['adx_rising']        = df['adx'] > df['adx'].shift(3)
    return df
```

### 4.5 ADX + DI

```python
def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = df.copy()
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(abs(df['high'] - df['close'].shift(1)),
                   abs(df['low']  - df['close'].shift(1)))
    )
    df['plus_dm']  = np.where(
        (df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
        np.maximum(df['high'] - df['high'].shift(1), 0), 0)
    df['minus_dm'] = np.where(
        (df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
        np.maximum(df['low'].shift(1) - df['low'], 0), 0)

    atr_s      = df['tr'].ewm(span=period, adjust=False).mean()
    plus_di_s  = 100 * df['plus_dm'].ewm(span=period, adjust=False).mean() / atr_s
    minus_di_s = 100 * df['minus_dm'].ewm(span=period, adjust=False).mean() / atr_s
    dx         = 100 * abs(plus_di_s - minus_di_s) / (plus_di_s + minus_di_s)

    df['adx']       = dx.ewm(span=period, adjust=False).mean()
    df['plus_di']   = plus_di_s
    df['minus_di']  = minus_di_s
    df['di_cross_bullish'] = (df['plus_di'] >  df['minus_di']) & \
                             (df['plus_di'].shift(1) <= df['minus_di'].shift(1))
    df['di_cross_bearish'] = (df['minus_di'] >  df['plus_di']) & \
                             (df['minus_di'].shift(1) <= df['plus_di'].shift(1))
    return df
```

### 4.6 Volumen y Velas de Reversal

```python
def detect_volume_signals(df: pd.DataFrame, vol_ema_period: int = 20) -> pd.DataFrame:
    df = df.copy()
    df['vol_ema']     = df['volume'].ewm(span=vol_ema_period, adjust=False).mean()
    df['vol_slope_3'] = (df['volume'] - df['volume'].shift(3)) / df['volume'].shift(3)
    df['vol_decreasing'] = (df['volume'] < df['vol_ema']) & \
                           (df['volume'] < df['volume'].shift(1)) & \
                           (df['vol_slope_3'] < 0)
    df['vol_increasing'] = (df['volume'] > df['vol_ema']) & \
                           (df['volume'] > df['volume'].shift(1)) & \
                           (df['vol_slope_3'] > 0)
    df['vol_entry_ok']   = df['volume'] >= df['vol_ema'] * 0.7
    return df


def detect_reversal_candles(df: pd.DataFrame) -> pd.DataFrame:
    df    = df.copy()
    body  = abs(df['close'] - df['open'])
    upper = df['high'] - df[['close', 'open']].max(axis=1)
    lower = df[['close', 'open']].min(axis=1) - df['low']
    total = df['high'] - df['low']

    df['is_gravestone']        = (upper > 2 * body) & (lower < body * 0.3) & (total > 0)
    df['is_dragonfly']         = (lower > 2 * body) & (upper < body * 0.3) & (total > 0)
    df['is_doji']              = body < (total * 0.10)
    df['is_red_candle']        = df['close'] < df['open']
    df['is_green_candle']      = df['close'] > df['open']
    df['high_lower_than_prev'] = df['high'] < df['high'].shift(1)
    df['low_higher_than_prev'] = df['low']  > df['low'].shift(1)
    return df
```

### 4.7 Interpretación de Velas con IA

```python
import anthropic, json

def interpret_candles_with_ai(symbol: str, timeframe: str) -> dict:
    """
    CACHÉ en memoria: si la vela de 15m no cerró desde la última
    llamada, devolver el resultado cacheado. NO llamar a la API.

    Costo estimado: ~$0.002/consulta × máx 96 ciclos/día = ~$0.19/día
    Con caché efectiva: ~$0.05/día en operación normal.

    Sprint 1: modo 'informative' — no bloquea entradas.
    Sprint 2: modo 'binding'    — puede vetar o reducir sizing.
    """
    df      = MEMORY_STORE[symbol][timeframe]['df']
    cur_bar = len(df)
    cache   = MEMORY_STORE[symbol][timeframe].get('ai_cache')
    cached_bar = MEMORY_STORE[symbol][timeframe].get('ai_cache_bar', -1)

    # Retornar caché si la vela no cambió
    if cache and cached_bar == cur_bar:
        return cache

    last     = df.iloc[-1]
    last_5   = df.tail(5)[['open', 'high', 'low', 'close', 'volume']].to_string(
                   float_format='{:.4f}'.format)
    regime   = MEMORY_STORE[symbol][timeframe].get('regime', {})
    zone     = get_fibonacci_zone(float(last['close']), last)

    prompt = f"""Eres un analista técnico experto en criptomonedas.
Analiza y responde ÚNICAMENTE en JSON válido, sin markdown ni texto extra.

CONTEXTO: Régimen={regime.get('category','?')} | Fase EMA20={last.get('ema20_phase','?')}
ADX={float(last.get('adx',0)):.1f} | Zona Fibonacci={zone}
Basis VWMA={float(last['basis']):.4f} | Upper5={float(last['upper_5']):.4f}
Lower5={float(last['lower_5']):.4f}

ÚLTIMAS 5 VELAS ({timeframe}):
{last_5}

JSON requerido:
{{"pattern_detected":"nombre","pattern_confidence":0.0,
  "market_sentiment":"bullish|bearish|indecision|reversal",
  "candle_interpretation":"máx 2 oraciones en español",
  "agrees_with_signal":true,
  "recommendation":"enter|wait|caution",
  "key_observation":"1 oración"}}"""

    client   = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        result = json.loads(response.content[0].text)
    except json.JSONDecodeError:
        result = {"pattern_detected": "unknown", "pattern_confidence": 0.5,
                  "market_sentiment": "indecision", "agrees_with_signal": True,
                  "recommendation": "wait", "candle_interpretation": "Error IA",
                  "key_observation": "No disponible"}

    # Guardar en caché de memoria
    MEMORY_STORE[symbol][timeframe]['ai_cache']     = result
    MEMORY_STORE[symbol][timeframe]['ai_cache_bar'] = cur_bar
    return result
```

### 4.8 Función maestra — calcular todo en memoria

```python
def calculate_all_indicators(df: pd.DataFrame,
                              cfg: dict,
                              symbol: str = '') -> pd.DataFrame:
    """
    Pipeline completo de indicadores. Input: OHLCV raw de Binance.
    Output: DataFrame enriquecido que vive en MEMORY_STORE.
    NO toca Supabase en ningún momento.
    """
    df = fibonacci_bollinger(df, length=cfg.get('length', 200),
                                  mult=cfg.get('mult', 3.0))
    df = calculate_macd_4c(df)
    df = calculate_emas(df)
    df = calculate_adx(df)
    df = detect_volume_signals(df, vol_ema_period=cfg.get('vol_ema_period', 20))
    df = detect_reversal_candles(df)

    regime_cfg = cfg.get('active_params', CONFIG_BY_RISK['riesgo_medio'])
    df = classify_ema20_phase(df,
            flat_pct        = regime_cfg['flat_pct'],
            peak_pct        = regime_cfg['peak_pct'],
            lookback_window = 100)
    return df
```

---

## 5. RÉGIMEN DINÁMICO DE MERCADO

*El régimen se calcula en memoria cada 15m. Solo se escribe en Supabase si cambia de categoría.*

```python
CONFIG_BY_RISK = {
    'alto_riesgo': {
        'mtf_threshold': 0.80, 'max_trades': 1,  'atr_mult': 2.5,
        'rr_min': 3.0,  'adx_min': 30, 'min_nivel_entrada': 2,
        'di_cross_required': True,  'flat_pct': 25.0, 'peak_pct': 75.0,
        'label': '🔴 Alto Riesgo'
    },
    'riesgo_medio': {
        'mtf_threshold': 0.65, 'max_trades': 3,  'atr_mult': 2.0,
        'rr_min': 2.5,  'adx_min': 20, 'min_nivel_entrada': 1,
        'di_cross_required': True,  'flat_pct': 20.0, 'peak_pct': 80.0,
        'label': '🟡 Riesgo Medio'
    },
    'bajo_riesgo': {
        'mtf_threshold': 0.50, 'max_trades': 5,  'atr_mult': 1.5,
        'rr_min': 2.0,  'adx_min': 15, 'min_nivel_entrada': 1,
        'di_cross_required': False, 'flat_pct': 15.0, 'peak_pct': 85.0,
        'label': '🟢 Bajo Riesgo'
    }
}
# Todos los valores son editables en el panel de Configuración.

def classify_market_risk(df: pd.DataFrame) -> dict:
    """
    Score 0-100. Pesos: ATR 35% + ADX 35% + Volumen 20% + Macro 10%.
    Calculado en MEMORIA. DB write solo si la categoría cambia.
    """
    last       = df.iloc[-1]
    atr_pct    = float((df['atr'].tail(50) < last['atr']).mean() * 100)
    adx_score  = max(0, 100 - float(last['adx']) * 2.5)
    vol_avg    = float(df['volume'].tail(20).mean())
    vol_ratio  = float(last['volume']) / vol_avg if vol_avg > 0 else 1.0
    vol_score  = max(0, min(100, (1.5 - vol_ratio) * 67))
    macro      = 80 if float(last['ema4']) < float(last['ema5']) else 20

    risk_score = atr_pct*0.35 + adx_score*0.35 + vol_score*0.20 + macro*0.10

    if   risk_score >= 65: category = 'alto_riesgo'
    elif risk_score >= 35: category = 'riesgo_medio'
    else:                  category = 'bajo_riesgo'

    return {
        'category':      category,
        'risk_score':    round(risk_score, 1),
        'active_params': CONFIG_BY_RISK[category],
        'label':         CONFIG_BY_RISK[category]['label'],
        'features': {
            'atr_percentile': round(atr_pct, 1),
            'adx_value':      round(float(last['adx']), 1),
            'volume_ratio':   round(vol_ratio, 2),
            'macro_trend':    'bearish' if macro == 80 else 'bullish',
        }
    }


async def update_regime_if_changed(symbol: str, new_regime: dict):
    """
    DB write SOLO si la categoría cambió respecto a la última registrada.
    Un mercado en riesgo_medio puede mantenerse así durante horas
    sin generar ninguna escritura.
    """
    prev = BOT_STATE['regime_cache'].get(symbol, {}).get('category')
    if prev == new_regime['category']:
        return  # Sin cambio → sin escritura

    # Cambió → escribir en Supabase y actualizar caché
    BOT_STATE['regime_cache'][symbol] = new_regime
    await supabase.table('regime_history').insert({
        'symbol':     symbol,
        'category':   new_regime['category'],
        'risk_score': new_regime['risk_score'],
        'features':   new_regime['features'],
        'changed_at': datetime.utcnow().isoformat()
    }).execute()
```

---

## 6. RULE ENGINE — MOTOR DE REGLAS

### 6.1 Reglas cargadas en memoria al inicio

```python
async def load_rules_to_memory() -> list[dict]:
    """
    Las reglas se leen de Supabase UNA vez al iniciar el worker
    y se cargan en memoria. No se consulta Supabase en cada ciclo.

    Si el usuario edita una regla en el panel, el frontend llama
    a un endpoint que actualiza Supabase Y recarga RULES_MEMORY.
    """
    result = await supabase.table('trading_rules')\
        .select('*')\
        .eq('enabled', True)\
        .eq('current', True)\
        .order('priority')\
        .execute()

    RULES_MEMORY = result.data
    log(f"Rule Engine: {len(RULES_MEMORY)} reglas cargadas en memoria")
    return RULES_MEMORY

RULES_MEMORY: list[dict] = []  # cargado al startup
```

### 6.2 Estructura JSON de regla en Supabase

```json
{
  "id":              1001,
  "rule_code":       "Aa13",
  "name":            "LONG — EMA50 cruza basis (macro bajista)",
  "direction":       "long",
  "ema50_vs_ema200": "below",
  "enabled":         true,
  "regime_allowed":  ["riesgo_medio", "bajo_riesgo"],
  "priority":        1,
  "confidence":      "high",
  "entry_trades":    [1],
  "conditions": [
    {"indicator": "ema4_cross_basis", "operator": "==", "value": true},
    {"indicator": "pinescript_signal","operator": "==", "value": "Buy"}
  ],
  "logic":   "AND",
  "notes":   "Al cruce comprar al primer Buy del PineScript",
  "version": 1,
  "current": true
}
```

### 6.3 Tablas Supabase para el Rule Engine

```sql
-- Tabla de reglas activas
CREATE TABLE trading_rules (
    id              BIGINT PRIMARY KEY,         -- numérico único irrepetible
    rule_code       VARCHAR(10) NOT NULL,       -- Aa11, Bb22, etc.
    name            TEXT NOT NULL,
    direction       VARCHAR(10),                -- 'long' | 'short'
    ema50_vs_ema200 VARCHAR(10),                -- 'above'|'below'|'any'
    enabled         BOOLEAN DEFAULT true,
    regime_allowed  JSONB,
    priority        INT DEFAULT 99,
    confidence      VARCHAR(10),
    entry_trades    JSONB,
    conditions      JSONB,
    logic           VARCHAR(5),                 -- 'AND' | 'OR'
    notes           TEXT,
    version         INT DEFAULT 1,
    current         BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Historial de versiones (control de cambios)
CREATE TABLE trading_rules_history (
    id               BIGSERIAL PRIMARY KEY,
    rule_id          BIGINT REFERENCES trading_rules(id),
    version          INT,
    changed_at       TIMESTAMPTZ DEFAULT NOW(),
    previous_config  JSONB,
    new_config       JSONB,
    reason           TEXT
);
```

---

## 7. FASE 4 — DECISIÓN DE ENTRADA LONG / SHORT

### 7.1 Pre-filtros universales

```
PRE-FILTROS (todos evaluados desde MEMORIA — sin consultas a DB):
  ✓ Señal PineScript activa: tradeDirection == "Buy" o "Sell"
  ✓ Señal vigente: signal_age <= MAX_SIGNAL_AGE_BARS (default 3, configurable)
  ✓ MTF score >= mtf_threshold del régimen activo
  ✓ Trades abiertos < max_trades del régimen activo
  ✓ RR real >= rr_min activo (ajustado por fees)
  ✓ Capital operativo suficiente para T1
  ✓ Símbolo NO en emergencia activa (BOT_STATE['emergency'][symbol])
  ✓ Circuit breaker NO activo (BOT_STATE['circuit_breaker']['triggered'])
  ✓ Cooldown NO activo (BOT_STATE['cooldowns'].get(symbol))
  ✓ vol_entry_ok == True (volumen >= 70% de vol_ema)
  ✓ Warm-up completado (len(df) >= 200)

PRE-FILTRO DE BASIS:
  LONG:  close <= basis_15m × 1.02
  SHORT: close >= basis_15m × 0.98
  Excepción: Aa12 (rebote lower_5/6) y Bb22 (agotamiento upper_6)
```

### 7.2 Condiciones LONG (lógica OR — primera cumplida = entrar)

```
══════════════════════════════════════════════════════════════
A. COMPRAR LONG — señal "Buy" PineScript (Nivel 1 o Nivel 2)
══════════════════════════════════════════════════════════════

RAMA A1 — EMA50 < EMA200 (macro bajista)

  [P1 — Alta] ⚡ Aa13
  ema4 cruza hacia ARRIBA basis_15m
  AND pinescript_signal == "Buy"
  → Comprar en el cruce. T1 × confluence_multiplier.

  [P2 — Media] 📍 Aa12
  (ema20_angle >= 0)
  AND (LOW cruzó lower_5 o lower_6 en últimas 3 velas)
  AND (is_dragonfly OR low_higher_than_prev)
  → T1

  [P3 — Media-Baja] 🔍 Aa11
  (ema20_angle >= 0) AND (adx < 20)
  AND (ema20_phase == 'nivel_1_long')
  AND (di_cross_bullish == True)
  → Solo régimen medio/bajo. T1 solo.

RAMA A2 — EMA50 > EMA200 (macro alcista)

  [P1 — Alta] ⚡ Aa24
  ema4 cruza hacia ARRIBA basis_15m
  AND (ema20_phase == 'nivel_1_long')
  → T1. Habilita T2/T3 con condición precio decreciente.

  [P2 — Alta] 📈 Aa22
  (ema50_angle >= 0) AND (ema4_precio >= basis_15m)
  → T1 × confluence_multiplier

  [P3 — Media] 📈 Aa23
  (ema9_angle >= 0) AND (ema50_angle >= 0)
  AND (adx >= adx_min del régimen)
  → T1

  [P4 — Media-Baja] 🔍 Aa21
  (ema20_angle >= 0) AND (adx < 20)
  AND (zona_fibonacci ENTRE -2 Y +2)
  AND (close <= basis_15m × 1.005)
  AND (solo régimen bajo_riesgo)
  → T1 solo
```

### 7.3 Condiciones SHORT (lógica OR)

```
══════════════════════════════════════════════════════════════
B. COMPRAR SHORT — señal "Sell" PineScript (Nivel -1 o -2)
══════════════════════════════════════════════════════════════
⚠️ EMA50 > EMA200: RR mínimo forzado 3.0, solo T1.

RAMA B1 — EMA50 < EMA200 (macro bajista)

  [P1 — Alta] ⚡ Bb12
  ema4 cruza hacia ABAJO basis_15m
  AND pinescript_signal == "Sell"
  → T1 × confluence_multiplier

  [P2 — Alta] 📉 Bb13
  (ema4_precio <= basis_15m) AND (adx < 20)
  AND (ema20_phase IN ['flat','nivel_1_short'])
  AND (di_cross_bearish) AND (ema20_angle <= 0)
  → T1

  [P3 — Media] 💪 Bb11
  (ema20_angle <= 0) AND (adx > 40)
  AND (ema20_phase == 'nivel_2_short')
  AND (minus_di > plus_di + 5)
  → Solo medio/bajo. T1 + habilita T2.

RAMA B2 — EMA50 > EMA200 (macro alcista — contra-tendencia)

  [P1 — Alta] ⚡ Bb22
  (high cruzó upper_6 en últimas 2 velas)
  AND (adx > 40) AND (ema20_phase == 'nivel_2_long')
  AND (ema50_angle <= 0)
  AND (is_gravestone OR (is_red_candle AND high_en_upper_6)
       OR high_lower_than_prev)
  → T1 solo. RR mínimo 3.0 forzado.

  [P2 — Alta] ⚡ Bb23
  ema4 cruza hacia ABAJO basis_15m
  AND (ema20_angle <= 0)
  → T1

  [P3 — Media] 💪 Bb21
  (ema20_angle <= 0) AND (adx > 40)
  AND (ema20_phase == 'nivel_2_short')
  AND (minus_di > plus_di + 10)
  AND (solo régimen bajo_riesgo)
  → T1. RR 3.0.
```

---

## 8. GESTIÓN DE CAPITAL Y SIZING

### 8.1 Configuración en panel (todos editables)

```
Capital Total:       [ $500 ]   (cualquier monto)
% para Trading:      [  20% ]   (5% - 100%)
──────────────────────────────────────────────
Capital Operativo:   $ 90       (= Capital × % × 0.90)
Buffer seguridad:    $ 10       (10% fijo para fees/slippage)

TRADES HABILITADOS (calculado automáticamente):
  Cap. Op. < $30    → 1 trade
  $30  - $60        → 2 trades
  $60  - $150       → 3 trades  ← caso $500 × 20%
  $150 - $300       → 4 trades
  > $300            → 5 trades

Distribución (editable, suma debe = 100%):
  3 trades: T1:[20%] T2:[30%] T3:[50%]
  5 trades: T1:[10%] T2:[15%] T3:[20%] T4:[25%] T5:[30%]

Validación: cada trade debe ser >= $15 (mínimo Binance).
Si no alcanza: bloquear ese trade y notificar en panel.
```

### 8.2 Sizing con confluence_multiplier

```python
BINANCE_MIN_ORDER = 15.0

def calculate_sizes(capital_op: float, n_trades: int,
                    regime: str, confluence_score: int,
                    distributions: dict) -> list[dict]:
    max_by_regime = {'alto_riesgo': 1, 'riesgo_medio': 3, 'bajo_riesgo': 5}
    effective_n   = min(n_trades, max_by_regime[regime])
    mult          = {1: 0.70, 2: 0.85, 3: 1.00}[confluence_score]
    dist          = distributions[effective_n]

    return [
        {'trade_n': i, 'usd': round(capital_op * p * mult, 2),
         'price_cond_long':  None if i==1 else f'close < t{i-1}_price',
         'price_cond_short': None if i==1 else f'close > t{i-1}_price'}
        for i, p in enumerate(dist, start=1)
        if capital_op * p * mult >= BINANCE_MIN_ORDER
    ]
```

---

## 9. GESTIÓN DE POSICIÓN

### 9.1 Estado de posición — WARM en Supabase

```python
# La posición vive en Supabase (WARM) Y en BOT_STATE (memoria).
# Al abrir: insert en Supabase + actualizar BOT_STATE
# Al cerrar: update en Supabase (closed_at, exit_price, pnl) + limpiar BOT_STATE
# En cada ciclo: NO consultar Supabase, leer desde BOT_STATE

@dataclass
class Position:
    symbol:       str
    side:         str          # 'long' | 'short'
    entries:      list         # lista de PositionEntry
    sl_price:     float        # actualizado tras cada entrada
    tp_partial:   float        # upper_5 o lower_5
    tp_full:      float        # upper_6 o lower_6
    is_open:      bool = True

    @property
    def avg_entry(self) -> float:
        total = sum(e.usd for e in self.entries)
        return sum(e.price * e.usd for e in self.entries) / total if total > 0 else 0

    def recalc_sl(self, atr: float, mult: float):
        """SL sobre precio promedio ponderado — nunca sobre T1."""
        avg = self.avg_entry
        self.sl_price = avg - atr*mult if self.side=='long' else avg + atr*mult

    def check_breakeven(self, price: float, fee: float = 0.001) -> bool:
        avg  = self.avg_entry
        risk = abs(avg - self.sl_price)
        if self.side == 'long'  and price >= avg + risk:
            self.sl_price = avg * (1 + fee); return True
        if self.side == 'short' and price <= avg - risk:
            self.sl_price = avg * (1 - fee); return True
        return False
```

### 9.2 Cierre parcial proporcional

```python
def get_partial_close_plan(position: Position) -> dict:
    """
    Trades pequeños (T1, T2) → cerrar en upper_5 (partial).
    Trade grande (T3) → cerrar en upper_6 / Nivel 3 (full).
    T3 siempre viaja al extremo más rentable.
    """
    n = len(position.entries)
    if n == 1:
        total = position.entries[0].usd
        return {'partial_usd': round(total*0.40,2), 'full_usd': round(total*0.60,2)}

    sorted_e  = sorted(position.entries, key=lambda e: e.usd)
    half      = (n // 2) + (1 if n % 2 else 0)
    return {
        'partial_usd':    sum(e.usd for e in sorted_e[:half]),
        'full_usd':       sum(e.usd for e in sorted_e[half:]),
        'partial_trades': [e.trade_n for e in sorted_e[:half]],
        'full_trades':    [e.trade_n for e in sorted_e[half:]],
    }
```

### 9.3 Take Profit con EMA50 vs EMA200 switch

```python
def evaluate_tp(df: pd.DataFrame, pos: Position) -> dict:
    last       = df.iloc[-1]
    price      = float(last['close'])
    trend_mode = float(last['ema4']) > float(last['ema5'])

    if pos.side == 'long':
        partial = price >= pos.tp_partial
        full    = price >= pos.tp_full
        if trend_mode:
            nivel3 = (last['ema20_phase'] == 'nivel_3_long' and
                      last['vol_decreasing'] and (
                      last['is_gravestone'] or last['high_lower_than_prev'] or
                      (last['is_red_candle'] and full)))
            return {'close_partial': partial, 'close_full': full and nivel3,
                    'mode': 'trend'}
        return {'close_partial': partial, 'close_full': full, 'mode': 'defensive'}

    else:  # short
        partial = price <= pos.tp_partial
        full    = price <= pos.tp_full
        if trend_mode:
            nivel3 = (last['ema20_phase'] == 'nivel_3_short' and
                      last['vol_increasing'] and (
                      last['is_dragonfly'] or last['low_higher_than_prev'] or
                      (last['is_green_candle'] and full)))
            return {'close_partial': partial, 'close_full': full and nivel3,
                    'mode': 'trend'}
        return {'close_partial': partial, 'close_full': full, 'mode': 'defensive'}
```

### 9.4 Flujo 2 pasos (cerrar → abrir)

```python
async def process_two_step(new_signal: str, price: float, symbol: str,
                            timestamp: datetime, rr_valid: bool,
                            sizes: list) -> list[dict]:
    """
    Regla: si hay posición contraria, SIEMPRE cerrar primero.
    Abrir solo si RR es válido. Si no: quedar flat.
    """
    orders = []
    pos    = BOT_STATE['positions'].get(symbol)

    if pos and pos.side != new_signal:
        orders.append({'step': 1, 'action': 'close', 'side': pos.side,
                       'price': price, 'reason': f'Señal {new_signal} opuesta'})
        await close_position_in_db(symbol, price, timestamp, reason='signal_reversal')

    if rr_valid:
        orders.append({'step': len(orders)+1, 'action': 'open',
                       'side': new_signal, 'price': price, 'sizes': sizes})
        await open_position_in_db(symbol, new_signal, price, sizes, timestamp)
    else:
        orders.append({'step': len(orders)+1, 'action': 'flat',
                       'reason': f'RR insuficiente — sistema en espera'})
    return orders
```

---

## 10. PROTECCIONES DE RIESGO

*Todas las protecciones se evalúan desde BOT_STATE (memoria). DB write solo en cambios de estado.*

### 10.1 Circuit Breaker

```python
async def check_circuit_breaker(pnl_usd: float, capital: float,
                                  config: dict) -> bool:
    """
    Evaluado cada vez que se cierra un trade.
    DB write: solo cuando se activa o se resetea (00:00 UTC).
    """
    BOT_STATE['circuit_breaker']['daily_pnl'] += pnl_usd
    daily_loss_pct = abs(min(BOT_STATE['circuit_breaker']['daily_pnl'], 0)) / capital * 100

    if daily_loss_pct >= config['max_daily_loss_pct']:
        BOT_STATE['circuit_breaker']['triggered'] = True
        await supabase.table('circuit_breaker_log').insert({
            'triggered_at':  datetime.utcnow().isoformat(),
            'daily_loss_pct': round(daily_loss_pct, 2),
            'resets_at':     '00:00 UTC'
        }).execute()
        return True
    return False
```

### 10.2 Cooldown, Max Holding, Correlación, Liquidación, Funding Rate

```python
# Cooldown: vive en BOT_STATE['cooldowns'][symbol]
# DB write: solo insert al activarlo + delete al expirar

# Max holding: evaluado desde BOT_STATE usando timestamps de posición
# DB write: ya existe en la posición abierta (entry_bar guardado al abrir)

# Correlación: calculado en memoria desde MEMORY_STORE[symbol]['15m']['df']
# DB write: NUNCA

# Precio de liquidación: calculado en memoria cada ciclo 5m
# DB write: NUNCA (solo alerta Telegram si SL > liq_price)

def calculate_liquidation_price(entry: float, leverage: int,
                                 side: str, mm: float = 0.005) -> float:
    if side == 'long':  return entry * (1 - 1/leverage + mm)
    else:               return entry * (1 + 1/leverage - mm)

# Funding rate: leído de Binance API en ciclo 5m → MEMORIA
# DB write: NUNCA
```

### 10.3 Monitor de Emergencia

```python
def check_emergency_ws(symbol: str, current_atr: float,
                        avg_atr: float, mult: float) -> bool:
    """
    Ejecutado en WebSocket (tiempo real).
    DB write: NUNCA — solo Telegram alert.
    Estado en BOT_STATE['emergency'][symbol] (memoria).
    """
    is_emergency = current_atr > avg_atr * mult
    BOT_STATE['emergency'][symbol] = is_emergency
    return is_emergency
```

---

## 11. INFRAESTRUCTURA Y DATAPROVIDER

### 11.1 DataProvider — solo Crypto en Sprint 1

```python
from abc import ABC, abstractmethod

class DataProvider(ABC):
    @abstractmethod
    async def get_ohlcv(self, symbol: str, timeframe: str,
                         limit: int) -> pd.DataFrame: pass
    @abstractmethod
    async def get_current_price(self, symbol: str) -> float: pass
    @abstractmethod
    async def place_order(self, symbol: str, side: str, size: float,
                           price: float = None, order_type: str = 'LIMIT') -> dict: pass
    @abstractmethod
    async def get_position(self, symbol: str) -> dict: pass
    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> dict: pass

class BinanceCryptoProvider(DataProvider):
    """Sprint 1 — único proveedor activo. Implementa SPOT y FUTURES."""
    def __init__(self, api_key: str, api_secret: str, market: str = 'futures'):
        self.market = market   # 'spot' | 'futures'
        # Inicializar cliente python-binance aquí

# API keys: NUNCA en código. Guardar en variables de entorno de Render.
# Permisos Binance: Reading + Trading. NUNCA Withdrawals.
# IP Whitelist: solo la IP del servidor Render.
```

### 11.2 Rate Limiter

```python
class RateLimiter:
    """Token bucket — usar máximo 50% del límite de Binance (600/min)."""
    def __init__(self, max_per_min: int = 600):
        self.tokens     = max_per_min
        self.max_tokens = max_per_min
        self.last       = time.time()

    def can_proceed(self) -> bool:
        elapsed = time.time() - self.last
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.max_tokens/60)
        self.last = time.time()
        if self.tokens >= 1:
            self.tokens -= 1; return True
        return False
```

### 11.3 Reconciliación (cada 45m — mínima escritura)

```python
async def reconcile(symbols: list, provider: DataProvider):
    """
    Compara BOT_STATE (memoria) vs Binance (fuente de verdad).
    DB write: solo si hay discrepancia (evento raro).
    """
    for symbol in symbols:
        real = await provider.get_position(symbol)
        bot  = BOT_STATE['positions'].get(symbol)
        if _positions_differ(real, bot):
            # Actualizar memoria
            BOT_STATE['positions'][symbol] = real
            # Insert en log (solo en discrepancias — no en cada ciclo)
            await supabase.table('reconciliation_log').insert({
                'symbol': symbol, 'bot_state': str(bot),
                'real_state': str(real), 'resolved_at': datetime.utcnow().isoformat()
            }).execute()
```

### 11.4 Health check de símbolo

```python
async def check_symbol_health(symbol: str, provider) -> bool:
    """Evaluado antes de abrir posición. Resultado en MEMORIA solo."""
    book   = await provider.get_order_book(symbol, limit=5)
    ticker = await provider.get_24hr_ticker(symbol)
    spread = (float(book['asks'][0][0]) - float(book['bids'][0][0])) / \
              float(book['bids'][0][0]) * 100
    vol24h = float(ticker['quoteVolume'])
    return vol24h > 1_000_000 and spread < 0.15  # configurable
```

---

## 12. ESTRATEGIA DE BASE DE DATOS — QUÉ SE GRABA Y QUÉ NO ⭐ NUEVO EN v4

### 12.1 Esquema completo de tablas Supabase

Solo existen **9 tablas**. Ningún OHLCV, ningún indicador calculado.

```sql
-- ══════════════════════════════════════════════════════
-- TABLAS WARM (estado operativo — upsert, 1 fila por entidad)
-- ══════════════════════════════════════════════════════

-- Estado actual de cada posición abierta
CREATE TABLE positions (
    id            BIGSERIAL PRIMARY KEY,
    symbol        VARCHAR(20) NOT NULL,
    market_type   VARCHAR(20),             -- 'spot' | 'futures'
    side          VARCHAR(10),             -- 'long' | 'short'
    entries       JSONB,                   -- [{trade_n, price, usd, rule_code, ts}]
    avg_entry     DECIMAL(20,8),
    sl_price      DECIMAL(20,8),
    tp_partial    DECIMAL(20,8),           -- upper_5 / lower_5
    tp_full       DECIMAL(20,8),           -- upper_6 / lower_6
    leverage      INT DEFAULT 1,
    liq_price     DECIMAL(20,8),
    breakeven_hit BOOLEAN DEFAULT false,
    mode          VARCHAR(10),             -- 'paper' | 'real'
    opened_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, mode)                   -- 1 posición abierta por símbolo
);

-- Estado del bot por símbolo (circuit breaker, cooldown, emergencia)
CREATE TABLE bot_state (
    symbol            VARCHAR(20) PRIMARY KEY,
    circuit_triggered BOOLEAN DEFAULT false,
    daily_pnl_usd     DECIMAL(10,2) DEFAULT 0,
    cooldown_expires  TIMESTAMPTZ,
    emergency_active  BOOLEAN DEFAULT false,
    last_updated      TIMESTAMPTZ DEFAULT NOW()
);

-- ══════════════════════════════════════════════════════
-- TABLAS COLD (histórico auditable — append only)
-- ══════════════════════════════════════════════════════

-- Trades cerrados (histórico completo)
CREATE TABLE trades (
    id               BIGSERIAL PRIMARY KEY,
    symbol           VARCHAR(20),
    side             VARCHAR(10),
    entry_avg        DECIMAL(20,8),
    exit_price       DECIMAL(20,8),
    sl_price         DECIMAL(20,8),
    tp_price         DECIMAL(20,8),
    pnl_usd          DECIMAL(10,4),
    pnl_pct          DECIMAL(8,4),
    exit_reason      VARCHAR(30),  -- 'tp_partial'|'tp_full'|'sl'|'timeout'|'manual'|'reversal'
    rule_code        VARCHAR(10),  -- Aa13, Bb22, etc.
    regime           VARCHAR(20),
    ema20_phase      VARCHAR(20),
    adx_value        DECIMAL(8,2),
    confluence_score INT,
    ai_recommendation VARCHAR(10),
    ai_agreed        BOOLEAN,
    signal_price     DECIMAL(20,8),    -- precio cuando se generó la señal
    execution_price  DECIMAL(20,8),    -- precio real de ejecución
    slippage_pct     DECIMAL(8,4),     -- para slippage tracking
    bars_held        INT,
    mode             VARCHAR(10),      -- 'paper' | 'real'
    opened_at        TIMESTAMPTZ,
    closed_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Log de señales detectadas (solo cuando Rule Engine dispara)
CREATE TABLE signals_log (
    id           BIGSERIAL PRIMARY KEY,
    symbol       VARCHAR(20),
    direction    VARCHAR(10),
    rule_code    VARCHAR(10),
    price        DECIMAL(20,8),
    zone         INT,
    regime       VARCHAR(20),
    ema20_phase  VARCHAR(20),
    adx          DECIMAL(8,2),
    acted_on     BOOLEAN,         -- ¿se abrió posición?
    reason_skip  TEXT,            -- por qué no se actuó (si acted_on=false)
    detected_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Historial de cambios de régimen
CREATE TABLE regime_history (
    id          BIGSERIAL PRIMARY KEY,
    symbol      VARCHAR(20),
    category    VARCHAR(20),
    risk_score  DECIMAL(5,1),
    features    JSONB,
    changed_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Log de reconciliaciones (solo cuando hay discrepancia)
CREATE TABLE reconciliation_log (
    id          BIGSERIAL PRIMARY KEY,
    symbol      VARCHAR(20),
    bot_state   JSONB,
    real_state  JSONB,
    resolved_at TIMESTAMPTZ DEFAULT NOW()
);

-- Circuit breaker log
CREATE TABLE circuit_breaker_log (
    id               BIGSERIAL PRIMARY KEY,
    triggered_at     TIMESTAMPTZ DEFAULT NOW(),
    daily_loss_pct   DECIMAL(5,2),
    daily_loss_usd   DECIMAL(10,2),
    resets_at        TEXT
);

-- Configuración del sistema (1 fila, upsert)
CREATE TABLE config (
    id              INT PRIMARY KEY DEFAULT 1,
    settings        JSONB NOT NULL,   -- todos los parámetros editables
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Rule Engine (ver sección 6)
-- trading_rules + trading_rules_history (ya definidas en sección 6)
```

### 12.2 Política de limpieza programada (sin OHLCV = mínima limpieza)

```python
# Como OHLCV nunca se guarda en Supabase, la limpieza es mínima.
# Solo limpiar logs históricos para evitar crecimiento indefinido.

CLEANUP_POLICY = {
    'signals_log':        180,  # días — 6 meses de señales
    'regime_history':     180,  # días
    'reconciliation_log': 90,   # días
    'circuit_breaker_log':365,  # días — 1 año
    # 'trades':  NUNCA borrar — histórico de negocio permanente
    # 'config':  NUNCA borrar — 1 fila
    # 'trading_rules': NUNCA borrar — versiones históricas valiosas
}

# Ejecutar 1 vez por semana (no diario — la tabla es pequeña)
async def cleanup_logs():
    for table, days in CLEANUP_POLICY.items():
        cutoff = datetime.utcnow() - timedelta(days=days)
        await supabase.table(table).delete().lt('created_at',
              cutoff.isoformat()).execute()

# Estimación de almacenamiento total con 4 símbolos:
# trades:           ~200 filas/mes × 12 = 2,400/año   → ~1 MB/año
# signals_log:      ~1,000 filas/mes                  → ~2 MB/6 meses
# regime_history:   ~200 filas/mes                    → ~0.5 MB/6 meses
# TOTAL:            < 10 MB después de 1 año completo
# (Supabase free: 500 MB → >50 años de margen)
```

### 12.3 Carga inicial de configuración al arrancar

```python
async def load_config_from_db() -> dict:
    """
    Al iniciar el worker: leer config de Supabase UNA vez → MEMORIA.
    Durante la operación: leer siempre desde MEMORY_CONFIG.
    Cuando el usuario edita en el panel: update Supabase + reload MEMORY_CONFIG.
    DB reads durante operación normal: CERO.
    """
    result = await supabase.table('config').select('settings').eq('id', 1).execute()
    MEMORY_CONFIG.update(result.data[0]['settings'])
    return MEMORY_CONFIG

MEMORY_CONFIG: dict = {}  # cargado al startup, referenciado en toda la operación
```

---

## 13. FRONTEND — NEXT.JS / REACT

### 13.1 Toggle Paper / Modo Real (login)

```
┌──────────────────────────────────────────────┐
│  eTrade                                      │
│  Usuario: [          ]  Pass: [          ]   │
│                                              │
│  Modo:  ○ 📄 PAPER  ●  🔴 REAL              │
│  ⚠️ Modo Real ejecuta órdenes en Binance.    │
│                              [Ingresar]      │
└──────────────────────────────────────────────┘
```

### 13.2 Panel de Configuración

```
MÓDULO CONFIGURACIÓN
══════════════════════════════════════════════════════

SECCIÓN 1 — CAPITAL Y SIZING
  Capital Total:     [ $500 ]     % Trading: [ 20% ]
  Capital Operativo: $90  (calc)  Trades:    HASTA 3 (calc)
  Distribución:      T1:[20%] T2:[30%] T3:[50%]

SECCIÓN 2 — PARÁMETROS POR RÉGIMEN
  ┌──────────────────────┬────────┬────────┬────────┐
  │ Parámetro            │🔴 Alto │🟡 Medio│🟢 Bajo │
  ├──────────────────────┼────────┼────────┼────────┤
  │ MTF Threshold        │[0.80]  │[0.65]  │[0.50]  │
  │ Max Trades           │[1]     │[3]     │[5]     │
  │ ATR Multiplier SL    │[2.5]   │[2.0]   │[1.5]   │
  │ RR Mínimo            │[3.0]   │[2.5]   │[2.0]   │
  │ ADX Mínimo           │[30]    │[20]    │[15]    │
  │ Nivel mín. entrada   │[2]     │[1]     │[1]     │
  │ DI Cross requerido   │[SÍ]    │[SÍ]    │[NO]    │
  │ EMA20 flat_pct       │[25]    │[20]    │[15]    │
  │ EMA20 peak_pct       │[75]    │[80]    │[85]    │
  └──────────────────────┴────────┴────────┴────────┘

SECCIÓN 3 — TIMEFRAMES Y SEÑALES
  Max velas por TF: 15m:[48] 30m:[48] 45m:[32] 4h:[30] 1d:[14] 1w:[8]
  Expiración señal PineScript: [3] velas

SECCIÓN 4 — PROTECCIONES
  Pérdida diaria máx: [5%]   Pérdida por trade máx: [2%]
  Cooldown post-SL:   [3] v  Cooldown post-TP:       [1] v
  Correlación máx:  [0.80]   Vol mínimo entrada:    [70%]

SECCIÓN 5 — ÓRDENES
  Tipo entrada: [Limit | Market]  Timeout: [2] velas  Gap SL: [0.10%]

SECCIÓN 6 — EMERGENCIA
  Activo: [SÍ]  ATR mult: [2.0]
  Acción: ○ Pausar  ● Alertar  ○ Cerrar todo

SECCIÓN 7 — MERCADO Y SÍMBOLOS
  Modo:    ○ Crypto SPOT  ● Crypto FUTURES
  Leverage (Futures): [5x]
  SPOT:    [BTC/USDT] [ETH/USDT] [SOL/USDT] [ADA/USDT] [+]
  FUTURES: [BTC/USDT] [ETH/USDT] [SOL/USDT] [ADA/USDT] [+]

SECCIÓN 8 — IA VELAS
  Activar: [SÍ]   Modo Sprint 1: Informativa (solo muestra, no bloquea)

SECCIÓN 9 — TELEGRAM
  Token: [**] Chat ID: [**]  [Probar]

SECCIÓN 10 — BACKUP
  [📥 Exportar]  [📤 Importar]  [↺ Defaults]
  Últimas 10 snapshots en config table.

[⚡ Reglas de Entrada]  ← abre ventana flotante Rule Engine
══════════════════════════════════════════════════════
```

### 13.3 Ventana flotante Rule Engine

```
┌──────────────────────────────────────────────────────────────┐
│  REGLAS DE ENTRADA              [+ LONG] [+ SHORT]    [×]   │
├────┬───────┬─────────────────────────┬──────┬──────┬────────┤
│ ID │ Cód.  │ Nombre                  │ Dir  │ ON   │ Acc.   │
├────┼───────┼─────────────────────────┼──────┼──────┼────────┤
│1001│ Aa11  │ EMA20+ADX bajo+DI cruce │ LONG │ ●ON  │ ✎ 🕐  │
│1002│ Aa12  │ Rebote lower_5/6        │ LONG │ ●ON  │ ✎ 🕐  │
│1003│ Aa13  │ EMA50 cruza basis ↑     │ LONG │ ●ON  │ ✎ 🕐  │
│1004│ Aa21  │ EMA50 angle + basis     │ LONG │ ●ON  │ ✎ 🕐  │
│1005│ Aa22  │ EMA50 asc + sobre basis │ LONG │ ●ON  │ ✎ 🕐  │
│1006│ Aa23  │ EMA9+EMA50 ascendentes  │ LONG │ ●ON  │ ✎ 🕐  │
│1007│ Aa24  │ EMA50+basis+Nivel1      │ LONG │ ●ON  │ ✎ 🕐  │
│1008│ Bb11  │ SHORT ADX fuerte macro↓ │SHORT │ ●ON  │ ✎ 🕐  │
│1009│ Bb12  │ EMA50 cruza basis ↓     │SHORT │ ●ON  │ ✎ 🕐  │
│1010│ Bb13  │ EMA50≤basis+ADX+DI      │SHORT │ ●ON  │ ✎ 🕐  │
│1011│ Bb21  │ SHORT ADX fuerte alcista│SHORT │ ●ON  │ ✎ 🕐  │
│1012│ Bb22  │ Agotamiento upper_6     │SHORT │ ●ON  │ ✎ 🕐  │
│1013│ Bb23  │ EMA50 cruza basis↓+EMA20│SHORT │ ●ON  │ ✎ 🕐  │
└────┴───────┴─────────────────────────┴──────┴──────┴────────┘
  ✎ = Editar condiciones  |  🕐 = Ver historial de versiones
```

### 13.4 Dashboard con Supabase Realtime (sin polling)

```typescript
// Suscripción a cambios — el dashboard se actualiza al instante
// cuando el worker Python escribe en Supabase
useEffect(() => {
  const sub = supabase.channel('trading')
    .on('postgres_changes', {event:'*', schema:'public', table:'positions'},
        p => setPositions(p.new))
    .on('postgres_changes', {event:'*', schema:'public', table:'bot_state'},
        p => setBotState(p.new))
    .on('postgres_changes', {event:'INSERT', schema:'public', table:'trades'},
        p => setLastTrade(p.new))
    .on('postgres_changes', {event:'INSERT', schema:'public', table:'signals_log'},
        p => setLastSignal(p.new))
    .subscribe()
  return () => sub.unsubscribe()
}, [])

// IMPORTANTE: el dashboard NO hace fetch periódico (polling).
// Solo recibe actualizaciones cuando el worker escribe en DB.
// Entre escrituras (puede ser horas sin señales) → cero tráfico.
```

**Layout del dashboard:**
```
┌────────────────────────────────────────────────────────────────┐
│ eTrade  📄 PAPER        🟡 Riesgo Medio  Score:48  ATR:52%    │
├────────────────────────────────────────────────────────────────┤
│ [BTC] [ETH] [SOL] [ADA]    [15m] [30m] [45m] [4h] [1D] [1W]  │
├─────────────────────────┬──────────────────────────────────────┤
│ FIBONACCI BB — BTC 15m  │ POSICIÓN                            │
│ 🎯 upper_6: $69,500     │ LONG ×2  Avg: $64,200              │
│    upper_5: $68,100 ←TP │ T1:$18@65k  T2:$27@63.4k           │
│ ── basis:   $65,000 ─── │ SL: $61,850 (prom.pond.)           │
│    lower_5: $61,900     │ Break-even: ❌ pendiente            │
│ 🎯 lower_6: $60,500     │ P&L: +$2.40 (+2.7%)               │
│                         │ Holding: 8/48 velas                 │
│ ZONA: +2 ↑  $65,800     │ [Cerrar Manual]                    │
├─────────────────────────┤                                      │
│ SEÑALES                 ├──────────────────────────────────────┤
│ Regla: Aa22 ⚡          │ IA VELAS                           │
│ EMA20: nivel_2_long     │ Doji en Upper_2  Conf:82%          │
│ ADX: 32  +DI>-DI ✓     │ "Pausa tras impulso. Posible       │
│ Confl: 3/3 TFs ✓        │  consolidación antes de continuar" │
│ Liq.price: $51,360      │ 📊 Informativa — no bloquea        │
├─────────────────────────┴──────────────────────────────────────┤
│ HOY  W:3  L:1  P&L:+$6.20  │  Emerg:OFF  CB:OFF  CD:OFF      │
│ LONG BTC Aa22 TP +$4.20 upper_5 ✓  Vol:✓                     │
└────────────────────────────────────────────────────────────────┘
```

---

## 14. NOTIFICACIONES TELEGRAM

```python
# DB write: NUNCA en las notificaciones. Solo Telegram.
EVENTS = {
    'trade_open':    '🟢 [{mode}] {side} {sym} @${price:.2f} | ${usd} | {rule} | {regime}',
    'tp_partial':    '📈 [{mode}] TP PARCIAL {sym} +${pnl:.2f} ({pct:.1f}%) | upper_5 ✓',
    'tp_full':       '🏆 [{mode}] TP TOTAL {sym} +${pnl:.2f} ({pct:.1f}%) | Nivel3 + Vol ✓',
    'sl':            '🔴 [{mode}] SL {sym} -${pnl:.2f} ({pct:.1f}%) | CD {bars}v',
    'emergency':     '🚨 EMERGENCIA {sym} ATR {ratio:.1f}x | Entradas pausadas',
    'circuit_break': '⚡ CIRCUIT BREAKER -{pct:.1f}% día | Pausa hasta 00:00 UTC',
    'reconcile':     '⚠️ DISCREPANCIA {sym} | Corregido automáticamente',
    'daily':         '📊 {date} | T:{n} W:{w} L:{l} | P&L:${pnl:.2f} | Cap:${cap:.2f}',
}
```

---

## 15. PAPER TRADING MODE

```
PAPER TRADING — comportamiento exacto:

Igual que MODO REAL en todas las fases excepto:
  → En lugar de place_order() → simular fill al close de la vela
  → Registrar en tabla 'trades' con mode='paper'
  → Telegram notifica con prefijo "[PAPER]"
  → Banner permanente en dashboard: "📄 MODO PAPER TRADING"
  → P&L, SL, TP, break-even, cierre parcial → todos simulados igual

TABLA trades (mode='paper'): incluye rule_code, regime, ema20_phase,
ai_recommendation, confluence_score → INPUT del dashboard de
performance del Sprint 2 (win rate por regla, etc.)
```

---

## 16. ENTREGABLES Y CRITERIOS DE ACEPTACIÓN — SPRINT 1

### 16.1 Entregables por módulo

| # | Módulo | Archivo | Resp. |
|---|--------|---------|-------|
| 1 | Memoria central + startup | `memory_store.py` | Backend |
| 2 | Fibonacci BB + zona | `fibonacci_bb.py` | Backend |
| 3 | MACD 4C + EMAs + EMA20 phases | `indicators.py` | Backend |
| 4 | ADX + DI | `adx.py` | Backend |
| 5 | Volumen + velas reversal | `volume_candles.py` | Backend |
| 6 | Régimen dinámico | `market_regime.py` | Backend |
| 7 | Rule Engine evaluator | `rule_engine.py` | Backend |
| 8 | Gestión posición + sizing | `position_manager.py` | Backend |
| 9 | Protecciones de riesgo | `risk_controls.py` | Backend |
| 10 | DataProvider Binance | `providers/binance.py` | Backend |
| 11 | WebSocket Manager | `ws_manager.py` | Backend |
| 12 | Ciclo 5m + ciclo 15m | `scheduler.py` | Backend |
| 13 | IA velas (con caché) | `ai_candles.py` | Backend |
| 14 | Reconciliación + Rate Limiter | `reconciliation.py` | Backend |
| 15 | Worker startup + warm-up | `startup.py` | Backend |
| 16 | Cleanup semanal | `data_cleanup.py` | Backend |
| 17 | Schema Supabase (9 tablas) | `schema.sql` | Full |
| 18 | API Routes Next.js | `pages/api/etrade/*` | Full |
| 19 | Panel Configuración | `pages/config.tsx` | Frontend |
| 20 | Ventana flotante Rule Engine | `components/RuleEngine.tsx` | Frontend |
| 21 | Dashboard Realtime | `pages/dashboard.tsx` | Frontend |
| 22 | Toggle Paper/Real (login) | `pages/login.tsx` | Frontend |
| 23 | Componente Fibonacci BB | `components/FibBBPanel.tsx` | Frontend |
| 24 | Telegram Notifier | `telegram.py` | Backend |
| 25 | Backup/Restore config | `components/ConfigBackup.tsx` | Frontend |

### 16.2 Criterios de aceptación

```
ARQUITECTURA DB:
  [ ] OHLCV raw NUNCA se escribe en Supabase
  [ ] Indicadores técnicos NUNCA se escriben en Supabase
  [ ] DB writes < 600 filas/día en operación normal con 4 símbolos
  [ ] Worker reiniciado recupera estado de negocio de Supabase < 30s
  [ ] Worker reiniciado reconstruye indicadores de Binance < 30s

FUNCIONALIDAD CORE:
  [ ] Pipeline completo < 3 segundos por símbolo
  [ ] 4 símbolos simultáneos sin degradación
  [ ] Régimen clasifica correctamente — DB write solo al cambiar
  [ ] EMA20 phases usan percentiles adaptativos (sin umbrales fijos)
  [ ] Basis multi-TF (15m, 4h, 1d) calcula confluence_score

GESTIÓN DE POSICIÓN:
  [ ] SL calculado sobre precio promedio ponderado (nunca sobre T1)
  [ ] Break-even activa en RR 1:1
  [ ] Cierre parcial: trades pequeños en upper_5, grande en upper_6
  [ ] Flujo 2 pasos: cierra siempre, abre solo si RR válido
  [ ] Modo defensivo (EMA50 < EMA200) cierra en upper_5/6 sin Nivel 3

PROTECCIONES:
  [ ] Circuit breaker pausa al superar pérdida diaria configurable
  [ ] Cooldown activo post-SL y post-TP
  [ ] Correlación > 0.80 bloquea entrada duplicada misma dirección
  [ ] Liq.price calculado y verificado vs SL antes de entrar
  [ ] Emergencia dispara cuando ATR > promedio × multiplicador

INFRAESTRUCTURA:
  [ ] WebSocket reconecta automáticamente
  [ ] Reconciliación detecta discrepancias (DB write solo si hay)
  [ ] Rate limiter < 50% del límite Binance
  [ ] Warm-up completo antes de activar señales
  [ ] IA velas usa caché — no llama API si vela no cambió

FRONTEND:
  [ ] Toggle Paper/Real en login funciona
  [ ] Configuración persiste en Supabase (tabla config, 1 fila)
  [ ] Rule Engine: crear, editar, versionar, revertir reglas
  [ ] Dashboard actualiza via Supabase Realtime (CERO polling)
  [ ] IA candlestick en modo Informativa

PAPER TRADING:
  [ ] Simula fills con precios reales de Binance
  [ ] Registra trades en tabla trades con mode='paper' y rule_code
  [ ] Telegram notifica con prefijo "[PAPER]"
```

---

## 17. HOJA DE RUTA SPRINTS 2 Y 3

```
SPRINT 2 — Calidad, análisis y optimización:
  ⬜ Backtesting (datos históricos de Binance — no de Supabase)
  ⬜ Walk-forward testing (70% in-sample / 30% out-of-sample)
  ⬜ Dashboard performance por regla (win rate Aa11, Aa22, etc.)
  ⬜ Rule Engine version control con comparación de performance
  ⬜ Modo Vinculante de IA velas (puede reducir sizing o vetar)
  ⬜ Optimización automática de parámetros por símbolo

SPRINT 3 — Expansión Forex:
  ⬜ DataProvider OANDA / Alpaca
  ⬜ Horarios de mercado Forex (24/5)
  ⬜ Swap rates overnight
  ⬜ Mismo análisis técnico — nuevos parámetros calibrados para Forex

SPRINT 4+ — Opciones (documento separado cuando corresponda)
```

---

## APÉNDICE — Comparativa v3 vs v4

| Aspecto | v3 | v4 |
|---------|----|----|
| OHLCV en Supabase | ✅ Sí (política de retención) | ❌ Nunca |
| Indicadores en Supabase | ✅ Sí | ❌ Nunca |
| Tablas Supabase | ~15 tablas | 9 tablas |
| Filas/día en DB | ~50,000 | < 600 |
| Almacenamiento / año | ~500 MB | < 10 MB |
| Recuperación tras reinicio | Leer DB | Leer DB (estado) + Binance (indicadores) |
| Latencia ciclo 15m | Sin cambio | Sin cambio |
| Dashboard | Polling | Supabase Realtime (sin polling) |
| Frecuencia Eventos Supabase Realtime | Baja (polling) | Alta (realtime 100ms) |

---

*Documento v4 — eTrade Plataforma de Trading Algorítmico*
*Antigravity Dev Team — Marzo 2026*
*v4.0 — Memory-First Architecture — Aprobado por Jhon (CEO)*
