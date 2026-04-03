# 🚀 ENGINEERING BRIEF v3 — eTrade: Plataforma de Trading Algorítmico Multi-Símbolo
## Proyecto: eTrade | Destino: Antigravity Dev Team
**Stack:** Python · Next.js · React · Supabase  
**Fecha:** Marzo 2026 | **Versión:** 3.0 — Documento maestro Sprint 1  
**Solicitado por:** Jhon (CEO)

---

## ÍNDICE

1. Objetivo y Alcance
2. Arquitectura de Tres Velocidades
3. Capa de Análisis Técnico
4. Régimen Dinámico de Mercado
5. Rule Engine — Motor de Reglas
6. Fase 4 — Decisión de Entrada LONG / SHORT
7. Gestión de Capital y Sizing
8. Gestión de Posición
9. Protecciones de Riesgo
10. Infraestructura y DataProvider
11. Frontend — Next.js / React
12. Notificaciones Telegram
13. Paper Trading Mode
14. Retención y Limpieza de Datos
15. Entregables y Criterios de Aceptación Sprint 1
16. Hoja de Ruta Sprints 2 y 3

---

## 1. OBJETIVO Y ALCANCE

### 1.1 Descripción del sistema

eTrade es una plataforma de trading algorítmico multi-símbolo que opera en mercados de **Crypto SPOT y Crypto FUTURES** (Binance). El sistema combina análisis técnico clásico (Fibonacci Bollinger Bands, ADX, EMAs), gestión dinámica de riesgo por régimen de mercado, un motor de reglas editable por el usuario, e interpretación contextual de velas mediante IA (Anthropic API).

### 1.2 Alcance Sprint 1

- **Mercados:** Crypto SPOT + Crypto FUTURES (Binance)
- **Símbolos iniciales:** BTC/USDT, ETH/USDT, SOL/USDT, ADA/USDT
- **Timeframes:** 5m (alertas), 15m (señales), 30m, 45m, 4h, 1d, 1w
- **Modo operativo:** Paper Trading (con precios reales Binance, sin ejecutar órdenes)
- **Toggle:** Paper Trading / Modo Real (Switch con login al inicio del sistema)

### 1.3 Fuera de scope Sprint 1

- Forex, Bolsa, Opciones → Sprint 3+
- Backtesting module → Sprint 2
- Walk-forward testing → Sprint 2
- Modo Vinculante de IA candlestick → Sprint 2 (después de validar en paper trading)

---

## 2. ARQUITECTURA DE TRES VELOCIDADES

### 2.1 Principio fundamental

**Las señales de ENTRADA solo se generan en el ciclo de 15m.**
**Las alertas de CIERRE pueden generarse en el ciclo de 5m.**
**El WebSocket solo alimenta el monitor de emergencia.**
**Nunca mezclar las tres velocidades en el mismo proceso.**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ARQUITECTURA DE TRES VELOCIDADES             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  VELOCIDAD 1 — WebSocket (tiempo real, continuo)                │
│  ─────────────────────────────────────────────                  │
│  Streams: ticker price + kline en formación                     │
│  Propósito ÚNICO: Monitor de emergencia ATR spike               │
│  NO procesa lógica de trading                                   │
│  Dispara: si ATR_actual > ATR_promedio × atr_emergency_mult     │
│                                                                  │
│  VELOCIDAD 2A — Ciclo de 5 minutos (Python scheduler)          │
│  ─────────────────────────────────────────────                  │
│  Propósito:                                                     │
│    → Re-evaluar precios de liquidación vs precio actual         │
│    → Re-evaluar condición de break-even                         │
│    → Verificar condición de CIERRE de posición abierta          │
│    → Leer funding rate acumulado (futuros)                      │
│    → Verificar órdenes parcialmente llenadas                    │
│    → Generar alertas de cierre si corresponde                   │
│    → Actualizar indicadores con velas de 5m para emergencias    │
│  NO genera señales de entrada nuevas                            │
│                                                                  │
│  VELOCIDAD 2B — Ciclo de 15 minutos (ciclo principal)          │
│  ─────────────────────────────────────────────                  │
│  Trigger: vela de 15m cerrada (is_kline_closed == true)        │
│  Propósito: LÓGICA COMPLETA                                     │
│    → Clasificación de régimen de mercado                        │
│    → Cálculo de todos los indicadores técnicos                  │
│    → Interpretación IA de velas                                 │
│    → Evaluación Rule Engine (señales de entrada)                │
│    → Decisión de apertura de posición                           │
│    → Actualización PositionManager en Supabase                  │
│    → Reconciliación bot vs exchange (cada 3 ciclos = 45m)       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 WebSocket Manager

```python
# Implementar con Python asyncio + websockets
# Streams por símbolo:
WEBSOCKET_STREAMS = {
    'BTC/USDT': [
        'btcusdt@kline_15m',   # velas 15m en formación
        'btcusdt@ticker',       # precio en tiempo real
    ],
    'ETH/USDT': ['ethusdt@kline_15m', 'ethusdt@ticker'],
    'SOL/USDT': ['solusdt@kline_15m', 'solusdt@ticker'],
    'ADA/USDT': ['adausdt@kline_15m', 'adausdt@ticker'],
}

# CRÍTICO: Solo procesar lógica completa cuando:
# kline['k']['x'] == True  (is_kline_closed)
# Antes de eso: solo actualizar precio para monitor de emergencia
```

---

## 3. CAPA DE ANÁLISIS TÉCNICO

### 3.1 Fibonacci Bollinger Bands — función core

**REFERENCIA PINESCRIPT ORIGINAL:**
```pinescript
f_fibonacci_bollinger(src, length, mult) =>
    basis_fb = ta.vwma(src, length)
    dev = mult * ta.stdev(src, length)
    upper_1 = basis_fb + (0.236 * dev)
    ...
    lower_6 = basis_fb - (1 * dev)
```

**IMPLEMENTACIÓN PYTHON:**
```python
import pandas as pd
import numpy as np

FIBONACCI_RATIOS = [0.236, 0.382, 0.500, 0.618, 0.764, 1.000]

def fibonacci_bollinger(df: pd.DataFrame,
                         length: int = 200,
                         mult: float = 3.0,
                         src_col: str = 'hlc3') -> pd.DataFrame:
    """
    CRÍTICO:
    1. Usar VWMA como basis (NO SMA) — equivale a ta.vwma de PineScript
    2. Usar ddof=0 en std (desviación de POBLACIÓN, igual a PineScript)
    3. src_col = 'hlc3' = (high + low + close) / 3
    """
    df = df.copy()
    if src_col == 'hlc3':
        df['hlc3'] = (df['high'] + df['low'] + df['close']) / 3

    src = df[src_col]

    # VWMA — basis principal (fuchsia en PineScript)
    typical_vol  = src * df['volume']
    df['basis']  = (
        typical_vol.rolling(window=length).sum() /
        df['volume'].rolling(window=length).sum()
    )

    # Desvío estándar de POBLACIÓN (ddof=0)
    dev = mult * src.rolling(window=length).std(ddof=0)

    for i, ratio in enumerate(FIBONACCI_RATIOS, start=1):
        df[f'upper_{i}'] = df['basis'] + ratio * dev
        df[f'lower_{i}'] = df['basis'] - ratio * dev

    return df


def get_fibonacci_zone(price: float, levels: dict) -> int:
    """
    Equivale a f_fibonacci_bollinger_nOp() del PineScript.
    CORRECCIÓN: el PineScript original tiene un bug donde la condición
    (nOp <= basis_fb or nOp > basis_fb) siempre retorna 0.
    En Python se evalúan primero los extremos.
    Retorna: -6 ... 0 ... +6
    """
    if price <= levels['lower_6']: return -6
    if price <  levels['lower_5']: return -5
    if price <  levels['lower_4']: return -4
    if price <  levels['lower_3']: return -3
    if price <  levels['lower_2']: return -2
    if price <  levels['lower_1']: return -1
    if price >  levels['upper_6']: return  6
    if price >  levels['upper_5']: return  5
    if price >  levels['upper_4']: return  4
    if price >  levels['upper_3']: return  3
    if price >  levels['upper_2']: return  2
    if price >  levels['upper_1']: return  1
    return 0
```

### 3.2 Basis Multi-Timeframe

El basis VWMA se calcula en 3 timeframes simultáneos y actúa como sistema de soporte/resistencia por importancia:

```python
# En el pipeline, calcular basis para cada TF disponible:
# basis_15m → nivel operativo (entradas inmediatas)
# basis_4h  → tendencia de sesión (pre-filtro principal)
# basis_1d  → contexto macro

def calculate_basis_confluence(price: float,
                                basis_15m: float,
                                basis_4h:  float,
                                basis_1d:  float,
                                direction: str) -> dict:
    """
    Calcula cuántos timeframes están alineados con la dirección.
    Afecta directamente el sizing de la entrada.

    direction: 'long' | 'short'
    """
    score = 0
    if direction == 'long':
        if price > basis_15m: score += 1
        if price > basis_4h:  score += 1
        if price > basis_1d:  score += 1
    else:
        if price < basis_15m: score += 1
        if price < basis_4h:  score += 1
        if price < basis_1d:  score += 1

    sizing_multiplier = {1: 0.70, 2: 0.85, 3: 1.00}

    return {
        'confluence_score':    score,          # 1, 2 o 3
        'sizing_multiplier':   sizing_multiplier[score],
        'description': (
            'Alta confluencia — 3 TFs alineados'  if score == 3 else
            'Confluencia media — 2 TFs alineados' if score == 2 else
            'Baja confluencia — 1 TF alineado'
        )
    }
```

### 3.3 MACD 4 Colores (4C)

```python
def calculate_macd_4c(df: pd.DataFrame,
                       fast: int = 12,
                       slow: int = 26,
                       signal: int = 9) -> pd.DataFrame:
    """
    Tipo de color:
      1 = MACD > 0 y subiendo  (bullish strong)
      2 = MACD > 0 y bajando   (bullish weak → señal Sell)
      3 = MACD < 0 y bajando   (bearish strong)
      4 = MACD < 0 y subiendo  (bearish weak → señal Buy)

    b_macd_buy  = tipo 4 después de 3,3
    b_macd_sell = tipo 2 después de 1,1
    """
    df = df.copy()
    ema_fast   = df['close'].ewm(span=fast,   adjust=False).mean()
    ema_slow   = df['close'].ewm(span=slow,   adjust=False).mean()
    df['macd'] = ema_fast - ema_slow

    conditions = [
        (df['macd'] >  0) & (df['macd'] >  df['macd'].shift(1)),
        (df['macd'] >  0) & (df['macd'] <= df['macd'].shift(1)),
        (df['macd'] <  0) & (df['macd'] <  df['macd'].shift(1)),
        (df['macd'] <  0) & (df['macd'] >= df['macd'].shift(1)),
    ]
    df['macd_4c'] = np.select(conditions, [1, 2, 3, 4], default=0)

    df['macd_buy'] = (
        (df['macd_4c'] == 4) &
        (df['macd_4c'].shift(1) == 3) &
        (df['macd_4c'].shift(2) == 3)
    )
    df['macd_sell'] = (
        (df['macd_4c'] == 2) &
        (df['macd_4c'].shift(1) == 1) &
        (df['macd_4c'].shift(2) == 1)
    )
    return df
```

### 3.4 EMAs y Ángulo EMA20 por Percentiles Adaptativos

```python
def calculate_emas(df: pd.DataFrame,
                   v1=3, v2=9, v3=20, v4=50, v5=200) -> pd.DataFrame:
    """
    EMA1=3, EMA2=9, EMA3=20 (filtro de ángulo),
    EMA4=50 (switch tendencia), EMA5=200 (macro)
    """
    df = df.copy()
    for i, span in enumerate([v1, v2, v3, v4, v5], start=1):
        df[f'ema{i}'] = df['close'].ewm(span=span, adjust=False).mean()
    return df


def classify_ema20_phase(df: pd.DataFrame,
                          lookback_window: int = 100,
                          flat_pct:  float = 20.0,
                          peak_pct:  float = 80.0,
                          atr_lookback: int = 10) -> pd.DataFrame:
    """
    Clasifica la fase del EMA20 usando PERCENTILES ADAPTATIVOS.

    En lugar de umbrales fijos (30°, 70°), usa la distribución histórica
    del propio activo/timeframe. Funciona igual para BTC/15m que SOL/4h.

    Fases LONG:
      'flat'         → ángulo cerca de 0 (percentil bajo)
      'nivel_1_long' → ángulo positivo emergente (percentil flat_pct a 50)
      'nivel_2_long' → ángulo positivo fuerte (percentil 50 a peak_pct)
      'nivel_3_long' → ángulo cayendo desde cima (agotamiento)

    Fases SHORT (simétricas):
      'nivel_1_short', 'nivel_2_short', 'nivel_3_short'

    IMPORTANTE: lookback_window, flat_pct y peak_pct son configurables
    en el panel por régimen de riesgo.
    """
    df = df.copy()

    # ATR para normalizar el ángulo (igual a f_angle del PineScript)
    df['atr'] = (
        df[['high', 'close']].max(axis=1) -
        df[['low',  'close']].min(axis=1)
    ).rolling(atr_lookback).mean()

    lookback_bars = 2
    df['ema20_angle_raw'] = np.degrees(
        np.arctan(
            (df['ema3'] - df['ema3'].shift(lookback_bars)) /
            (df['atr'] * lookback_bars + 1e-10)
        )
    )

    # Percentil ROLLING — esto es lo que hace el sistema adaptativo
    df['ema20_pct'] = (
        df['ema20_angle_raw']
        .rolling(lookback_window)
        .rank(pct=True) * 100
    )

    # Zona plana: ángulo en el 20% más bajo de su historia reciente
    flat_std = df['ema20_angle_raw'].rolling(lookback_window).std()
    is_flat  = df['ema20_angle_raw'].abs() < (flat_std * 0.3)

    # Detectar cima: ángulo bajando desde un máximo reciente
    peak_window = 5
    df['ema20_peak'] = df['ema20_angle_raw'].rolling(peak_window).max()
    falling_from_peak = (
        (df['ema20_angle_raw'] > 0) &
        (df['ema20_angle_raw'] < df['ema20_peak']) &
        (df['ema20_pct'] >= peak_pct * 0.6)
    )

    conditions = [
        is_flat,
        (~is_flat) & (df['ema20_angle_raw'] > 0) & (df['ema20_pct'] >= flat_pct)  & (df['ema20_pct'] < 50),
        (~is_flat) & (df['ema20_angle_raw'] > 0) & (df['ema20_pct'] >= 50)        & (df['ema20_pct'] < peak_pct),
        (~is_flat) & (df['ema20_angle_raw'] > 0) & falling_from_peak,
        (~is_flat) & (df['ema20_angle_raw'] < 0) & (df['ema20_pct'] <= (100-flat_pct)) & (df['ema20_pct'] > 50),
        (~is_flat) & (df['ema20_angle_raw'] < 0) & (df['ema20_pct'] <= 50)         & (df['ema20_pct'] > (100-peak_pct)),
        (~is_flat) & (df['ema20_angle_raw'] < 0) & falling_from_peak,
    ]
    phases = [
        'flat',
        'nivel_1_long', 'nivel_2_long', 'nivel_3_long',
        'nivel_1_short', 'nivel_2_short', 'nivel_3_short',
    ]
    df['ema20_phase'] = np.select(conditions, phases, default='flat')

    # Detección de transición desde plano
    df['was_flat_recently'] = (
        df['ema20_phase'].shift(1).isin(['flat']) |
        df['ema20_phase'].shift(2).isin(['flat']) |
        df['ema20_phase'].shift(3).isin(['flat'])
    )
    df['adx_rising'] = df['adx'] > df['adx'].shift(3)

    return df
```

### 3.5 ADX + DI

```python
def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    ADX: fuerza de tendencia (0-100, sin importar dirección)
    +DI: fuerza del movimiento alcista
    -DI: fuerza del movimiento bajista
    """
    df = df.copy()
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low']  - df['close'].shift(1))
        )
    )
    df['plus_dm']  = np.where(
        (df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
        np.maximum(df['high'] - df['high'].shift(1), 0), 0
    )
    df['minus_dm'] = np.where(
        (df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
        np.maximum(df['low'].shift(1) - df['low'], 0), 0
    )

    atr_s      = df['tr'].ewm(span=period, adjust=False).mean()
    plus_di_s  = 100 * df['plus_dm'].ewm(span=period, adjust=False).mean() / atr_s
    minus_di_s = 100 * df['minus_dm'].ewm(span=period, adjust=False).mean() / atr_s
    dx         = 100 * abs(plus_di_s - minus_di_s) / (plus_di_s + minus_di_s)

    df['adx']      = dx.ewm(span=period, adjust=False).mean()
    df['plus_di']  = plus_di_s
    df['minus_di'] = minus_di_s

    df['di_cross_bullish'] = (
        (df['plus_di'] >  df['minus_di']) &
        (df['plus_di'].shift(1) <= df['minus_di'].shift(1))
    )
    df['di_cross_bearish'] = (
        (df['minus_di'] >  df['plus_di']) &
        (df['minus_di'].shift(1) <= df['plus_di'].shift(1))
    )
    return df
```

### 3.6 Detección de Agotamiento de Volumen

```python
def detect_volume_signals(df: pd.DataFrame,
                            vol_ema_period: int = 20) -> pd.DataFrame:
    """
    Para confirmar Take Profit y señales de entrada.

    vol_decreasing → confirma LONG TP (agotamiento alcista)
    vol_increasing → confirma SHORT TP (presión vendedora)
    vol_entry_ok   → confirma que hay suficiente liquidez para entrar
    """
    df = df.copy()
    df['vol_ema']     = df['volume'].ewm(span=vol_ema_period, adjust=False).mean()
    df['vol_slope_3'] = (df['volume'] - df['volume'].shift(3)) / df['volume'].shift(3)

    df['vol_decreasing'] = (
        (df['volume'] < df['vol_ema']) &
        (df['volume'] < df['volume'].shift(1)) &
        (df['vol_slope_3'] < 0)
    )
    df['vol_increasing'] = (
        (df['volume'] > df['vol_ema']) &
        (df['volume'] > df['volume'].shift(1)) &
        (df['vol_slope_3'] > 0)
    )
    # Mínimo 70% del promedio para confirmar entrada con liquidez
    df['vol_entry_ok'] = df['volume'] >= df['vol_ema'] * 0.7

    return df
```

### 3.7 Detección de Velas de Reversal

```python
def detect_reversal_candles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Patrones de vela para confirmar cierre de posición y señales IA.
    """
    df = df.copy()
    body  = abs(df['close'] - df['open'])
    upper = df['high'] - df[['close', 'open']].max(axis=1)
    lower = df[['close', 'open']].min(axis=1) - df['low']
    total = df['high'] - df['low']

    # Lápida (Gravestone Doji): upper shadow > 2x body, en zona alcista
    df['is_gravestone'] = (
        (upper > 2 * body) &
        (lower < body * 0.3) &
        (total > 0)
    )
    # Libélula (Dragonfly Doji): lower shadow > 2x body, en zona bajista
    df['is_dragonfly'] = (
        (lower > 2 * body) &
        (upper < body * 0.3) &
        (total > 0)
    )
    # Doji genérico: body < 10% del rango total
    df['is_doji'] = body < (total * 0.10)

    # Vela roja en upper_6: close < open Y high estaba en upper_6
    df['is_red_candle']   = df['close'] < df['open']
    df['is_green_candle'] = df['close'] > df['open']

    # HIGH no supera vela anterior (agotamiento alcista)
    df['high_lower_than_prev'] = df['high'] < df['high'].shift(1)
    # LOW supera vela anterior hacia abajo (agotamiento bajista)
    df['low_higher_than_prev'] = df['low'] > df['low'].shift(1)

    return df
```

### 3.8 Interpretación de Velas con IA (Anthropic API)

```python
import anthropic
import json

def interpret_candles_with_ai(
    df: pd.DataFrame,
    levels: dict,
    regime: dict,
    ema20_phase: str,
    adx_value: float,
    signal_direction: str,  # 'Buy', 'Sell', or None
    mode: str = 'informative'  # 'informative' (Sprint 1) | 'binding' (Sprint 2)
) -> dict:
    """
    Segunda opinión contextual sobre el comportamiento del mercado.

    Sprint 1: modo 'informative' — muestra interpretación pero NO bloquea entrada.
    Sprint 2: modo 'binding'    — puede reducir sizing o vetar entrada.

    COSTO ESTIMADO: ~$0.002/consulta × 96 ciclos/día = ~$0.19/día

    CACHE: si la vela de 15m no cerró desde la última consulta,
    devolver el resultado cacheado (no llamar a la API).
    """
    # Construir tabla de las últimas 5 velas
    last_5 = df.tail(5)[['open', 'high', 'low', 'close', 'volume']].copy()
    candles_table = last_5.to_string(float_format='{:.4f}'.format)

    prompt = f"""Eres un analista técnico experto en criptomonedas.
Analiza las siguientes velas y el contexto de mercado.
Responde ÚNICAMENTE en JSON válido sin markdown ni texto adicional.

CONTEXTO:
- Régimen de mercado: {regime['category']} (score: {regime['risk_score']})
- Fase EMA20: {ema20_phase}
- ADX: {adx_value:.1f}
- Señal del sistema: {signal_direction or 'Ninguna'}
- Zona Fibonacci actual: {levels.get('zone', 0)}
- Basis (VWMA): {levels.get('basis', 0):.4f}
- Upper_5: {levels.get('upper_5', 0):.4f} | Upper_6: {levels.get('upper_6', 0):.4f}
- Lower_5: {levels.get('lower_5', 0):.4f} | Lower_6: {levels.get('lower_6', 0):.4f}

ÚLTIMAS 5 VELAS (15m):
{candles_table}

Responde con este JSON exacto:
{{
  "pattern_detected": "nombre_del_patron",
  "pattern_confidence": 0.0,
  "market_sentiment": "bullish|bearish|indecision|reversal",
  "candle_interpretation": "descripción en español de máximo 2 oraciones",
  "agrees_with_signal": true,
  "recommendation": "enter|wait|caution",
  "key_observation": "observación principal en una oración"
}}"""

    client   = anthropic.Anthropic()
    response = client.messages.create(
        model      = "claude-sonnet-4-20250514",
        max_tokens = 300,
        messages   = [{"role": "user", "content": prompt}]
    )

    try:
        result = json.loads(response.content[0].text)
    except json.JSONDecodeError:
        result = {
            "pattern_detected":    "unknown",
            "pattern_confidence":  0.5,
            "market_sentiment":    "indecision",
            "candle_interpretation": "No se pudo interpretar",
            "agrees_with_signal":  True,
            "recommendation":      "wait",
            "key_observation":     "Error en interpretación IA"
        }

    result['mode']  = mode
    result['model'] = 'claude-sonnet-4-20250514'
    return result
```

---

## 4. RÉGIMEN DINÁMICO DE MERCADO

### 4.1 Clasificación automática cada 15 minutos

```python
CONFIG_BY_RISK = {
    'alto_riesgo': {
        'mtf_threshold':      0.80,
        'max_trades':         1,
        'atr_mult':           2.5,
        'rr_min':             3.0,
        'adx_min':            30,
        'min_nivel_entrada':  2,
        'di_cross_required':  True,
        'flat_pct':           25.0,
        'peak_pct':           75.0,
        'label':              '🔴 Alto Riesgo',
    },
    'riesgo_medio': {
        'mtf_threshold':      0.65,
        'max_trades':         3,
        'atr_mult':           2.0,
        'rr_min':             2.5,
        'adx_min':            20,
        'min_nivel_entrada':  1,
        'di_cross_required':  True,
        'flat_pct':           20.0,
        'peak_pct':           80.0,
        'label':              '🟡 Riesgo Medio',
    },
    'bajo_riesgo': {
        'mtf_threshold':      0.50,
        'max_trades':         5,
        'atr_mult':           1.5,
        'rr_min':             2.0,
        'adx_min':            15,
        'min_nivel_entrada':  1,
        'di_cross_required':  False,
        'flat_pct':           15.0,
        'peak_pct':           85.0,
        'label':              '🟢 Bajo Riesgo',
    }
}
# NOTA: Todos estos valores son EDITABLES en el panel de Configuración de eTrade.

def classify_market_risk(df: pd.DataFrame) -> dict:
    """
    Score de riesgo 0-100 (bajo = mercado favorable, alto = mercado hostil).

    Pesos:
      ATR percentile  35% → volatilidad relativa alta = más riesgo
      ADX score       35% → tendencia débil = más riesgo
      Volume ratio    20% → volumen bajo = más riesgo
      Macro trend     10% → EMA50 < EMA200 = más riesgo
    """
    last = df.iloc[-1]

    atr_pct    = float((df['atr'].tail(50) < last['atr']).mean() * 100)
    adx_score  = max(0, 100 - float(last['adx']) * 2.5)
    vol_avg    = float(df['volume'].tail(20).mean())
    vol_ratio  = float(last['volume']) / vol_avg if vol_avg > 0 else 1.0
    vol_score  = max(0, min(100, (1.5 - vol_ratio) * 67))
    macro      = 80 if float(last['ema4']) < float(last['ema5']) else 20

    risk_score = (atr_pct*0.35 + adx_score*0.35 + vol_score*0.20 + macro*0.10)

    if   risk_score >= 65: category = 'alto_riesgo'
    elif risk_score >= 35: category = 'riesgo_medio'
    else:                  category = 'bajo_riesgo'

    cfg = CONFIG_BY_RISK[category]

    return {
        'category':      category,
        'risk_score':    round(risk_score, 1),
        'label':         cfg['label'],
        'active_params': cfg,
        'evaluated_at':  datetime.utcnow().isoformat(),
        'features': {
            'atr_percentile': round(atr_pct, 1),
            'adx_value':      round(float(last['adx']), 1),
            'volume_ratio':   round(vol_ratio, 2),
            'macro_trend':    'bearish' if macro == 80 else 'bullish',
        }
    }
```

### 4.2 Monitor de emergencia ATR spike

```python
EMERGENCY_CONFIG = {
    'enabled':           True,         # editable en Configuración
    'atr_multiplier':    2.0,          # Si ATR > promedio × este valor → emergencia
    'action':            'pause',      # 'pause' | 'close_all' | 'alert_only'
    # Editable en Configuración
}

def check_emergency(current_price: float,
                    current_atr:   float,
                    avg_atr:       float,
                    config:        dict) -> dict:
    """
    Ejecutado en el WebSocket (tiempo real).
    """
    is_emergency = current_atr > avg_atr * config['atr_multiplier']
    return {
        'emergency_active': is_emergency,
        'atr_ratio':        round(current_atr / avg_atr, 2),
        'action':           config['action'] if is_emergency else None,
    }
```

---

## 5. RULE ENGINE — MOTOR DE REGLAS

### 5.1 Estructura JSON en Supabase

```json
{
  "id":              1001,
  "rule_code":       "Aa13",
  "name":            "LONG — EMA50 cruza basis (macro bajista)",
  "description":     "EMA50 supera la VWMA (basis) en mercado macro bajista. Señal de cambio de tendencia local.",
  "direction":       "long",
  "market_type":     ["crypto_spot", "crypto_futures"],
  "ema50_vs_ema200": "below",
  "enabled":         true,
  "regime_allowed":  ["riesgo_medio", "bajo_riesgo"],
  "priority":        1,
  "confidence":      "high",
  "entry_trades":    [1],
  "conditions": [
    {"indicator": "ema4_cross_basis", "operator": "==", "value": true},
    {"indicator": "pinescript_signal", "operator": "==", "value": "Buy"}
  ],
  "logic":           "AND",
  "notes":           "Al momento del cruce comprar al primer señal de Buy",
  "created_at":      "2026-03-01T00:00:00Z",
  "updated_at":      "2026-03-01T00:00:00Z",
  "version":         1,
  "current":         true
}
```

### 5.2 Tabla de reglas en Supabase

```sql
-- Tabla principal de reglas
CREATE TABLE trading_rules (
    id              BIGINT PRIMARY KEY,    -- numérico único e irrepetible
    rule_code       VARCHAR(10) NOT NULL,  -- Aa11, Aa12, Bb21, etc.
    name            TEXT NOT NULL,
    description     TEXT,
    direction       VARCHAR(10),           -- 'long' | 'short'
    market_type     JSONB,
    ema50_vs_ema200 VARCHAR(10),           -- 'above' | 'below' | 'any'
    enabled         BOOLEAN DEFAULT true,
    regime_allowed  JSONB,
    priority        INT DEFAULT 99,
    confidence      VARCHAR(10),
    entry_trades    JSONB,
    conditions      JSONB,
    logic           VARCHAR(5),            -- 'AND' | 'OR'
    notes           TEXT,
    version         INT DEFAULT 1,
    current         BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Historial de versiones (control de cambios)
CREATE TABLE trading_rules_history (
    id                  BIGSERIAL PRIMARY KEY,
    rule_id             BIGINT REFERENCES trading_rules(id),
    version             INT,
    changed_at          TIMESTAMPTZ DEFAULT NOW(),
    changed_by          TEXT,
    previous_config     JSONB,
    new_config          JSONB,
    reason              TEXT,
    performance_before  JSONB,  -- win_rate, rr_avg al momento del cambio
    performance_after   JSONB   -- se actualiza después de N trades
);
```

### 5.3 UI — Ventana flotante de reglas

```
BOTÓN EN CONFIGURACIÓN: [⚡ Reglas de Entrada]
Abre ventana flotante modal con:

┌──────────────────────────────────────────────────────────────────┐
│  REGLAS DE ENTRADA                    [+ LONG] [+ SHORT] [×]    │
├────┬────────┬────────────────────────┬──────┬────────┬──────────┤
│ ID │ Código │ Nombre                 │ Dir  │ Estado │ Acciones │
├────┼────────┼────────────────────────┼──────┼────────┼──────────┤
│1001│ Aa11   │ EMA20+ADX bajo+DI cruz.│ LONG │  ●ON  │ ✎ 🕐 🗑 │
│1002│ Aa12   │ Rebote lower_5/6       │ LONG │  ●ON  │ ✎ 🕐 🗑 │
│1003│ Aa13   │ EMA50 cruza basis      │ LONG │  ●ON  │ ✎ 🕐 🗑 │
│1004│ Aa21   │ EMA50 angle+basis      │ LONG │  ●ON  │ ✎ 🕐 🗑 │
│1005│ Aa22   │ EMA50 asc + sobre basis│ LONG │  ●ON  │ ✎ 🕐 🗑 │
│1006│ Aa23   │ EMA9+EMA50 ascendentes │ LONG │  ●ON  │ ✎ 🕐 🗑 │
│1007│ Aa24   │ EMA50+basis+Nivel1     │ LONG │  ●ON  │ ✎ 🕐 🗑 │
│1008│ Bb11   │ SHORT ADX fuerte macro │SHORT │  ●ON  │ ✎ 🕐 🗑 │
│1009│ Bb12   │ EMA50 cruza basis↓     │SHORT │  ●ON  │ ✎ 🕐 🗑 │
│1010│ Bb13   │ EMA50≤basis+ADX+DI    │SHORT │  ●ON  │ ✎ 🕐 🗑 │
│1011│ Bb21   │ SHORT ADX fuerte alcist│SHORT │  ●ON  │ ✎ 🕐 🗑 │
│1012│ Bb22   │ Agotamiento upper_6    │SHORT │  ●ON  │ ✎ 🕐 🗑 │
│1013│ Bb23   │ EMA50 cruza basis↓+20  │SHORT │  ●ON  │ ✎ 🕐 🗑 │
└────┴────────┴────────────────────────┴──────┴────────┴──────────┘
  ✎ = Editar  |  🕐 = Ver historial de versiones  |  🗑 = Desactivar

Al hacer ✎ Editar → formulario con:
  Condición: [Indicador] [Operador >=,<=,==,>,<,crosses] [Valor]
  Lógica entre condiciones: [AND] [OR]
  Régimen permitido: [☑ Alto] [☑ Medio] [☑ Bajo]
  Trades habilitados: [☑ T1] [☑ T2] [☑ T3]
  [Guardar] [Cancelar]
  Al guardar: se crea nueva versión en trading_rules_history
```

---

## 6. FASE 4 — DECISIÓN DE ENTRADA LONG / SHORT

### 6.1 Pre-filtros universales (aplican SIEMPRE)

```
PRE-FILTROS — evaluar antes de cualquier condición A o B:
  ✓ Señal PineScript activa: tradeDirection == "Buy" o "Sell"
  ✓ Señal PineScript vigente: signal_age <= MAX_SIGNAL_AGE_BARS (default 3)
  ✓ MTF score >= mtf_threshold del régimen activo
  ✓ Trades abiertos en este símbolo < max_trades del régimen activo
  ✓ RR real >= rr_min activo (con fees incluidos)
     rr_real = (fibonacci_tp - entry_fee_adjusted) / (entry_fee_adjusted - sl)
  ✓ Capital operativo suficiente para la siguiente entrada
  ✓ Símbolo NO en emergencia activa
  ✓ Circuit breaker diario NO alcanzado
  ✓ Cooldown post-SL o post-TP NO activo
  ✓ Volumen de entrada: vol_entry_ok == True (≥ 70% del vol_ema)
  ✓ Health check del símbolo pasado
  ✓ Warm-up period completado (200 velas mínimo)

PRE-FILTRO DE BASIS (dirección):
  Para LONG:  close <= basis_15m × 1.02  (no entrar muy lejos del basis)
  Para SHORT: close >= basis_15m × 0.98
  EXCEPCIÓN: condiciones Aa12 (rebote lower_5/6) y Bb22 (agotamiento upper_6)
             no requieren este filtro por definición
```

### 6.2 Expiración de señal PineScript

```python
MAX_SIGNAL_AGE_BARS = 3  # configurable en Configuración

def is_signal_valid(signal_bar_index: int, current_bar_index: int) -> bool:
    return (current_bar_index - signal_bar_index) <= MAX_SIGNAL_AGE_BARS
```

### 6.3 Condiciones de entrada LONG

**LÓGICA: cualquiera de estas condiciones activa la compra (OR)**

```
══════════════════════════════════════════════════════════════════
A. COMPRAR LONG — señal "Buy" del PineScript (Nivel 1 o Nivel 2)
══════════════════════════════════════════════════════════════════

RAMA A1 — EMA50 < EMA200 (macro bajista → más selectivo)
  Evaluar en orden de prioridad. Primera cumplida = entrar.

  [PRIORIDAD 1 — Confianza ALTA] ⚡ ID: Aa13
  EMA50 cruza hacia ARRIBA el basis (VWMA)
  → Condición: ema4_crosses_above_basis == True
               AND pinescript_signal == "Buy"
  → Al momento del cruce, comprar al primer "Buy"
  → Sizing: T1 × sizing_multiplier(confluence_score)
  → Razón: en macro bajista, EMA50 superando basis es la señal
            más fuerte de cambio de tendencia local

  [PRIORIDAD 2 — Confianza MEDIA] 📍 ID: Aa12
  (ema20_angle >= 0)
  AND (LOW del precio cruzó lower_5 o lower_6 en últimas 3 velas)
  AND confirmación: is_dragonfly OR low_higher_than_prev
  → Rebote desde zona de sobreventa extrema
  → Sizing: T1

  [PRIORIDAD 3 — Confianza MEDIA-BAJA] 🔍 ID: Aa11
  (ema20_angle >= 0)
  AND (adx < 20)
  AND (ema20_phase == 'nivel_1_long')
  AND (di_cross_bullish == True)
  → Solo en régimen riesgo_medio o bajo_riesgo
  → Sizing: solo T1

RAMA A2 — EMA50 > EMA200 (macro alcista → más permisivo)

  [PRIORIDAD 1 — Confianza ALTA] ⚡ ID: Aa24
  EMA50 cruza hacia ARRIBA el basis (VWMA)
  AND (ema20_phase == 'nivel_1_long')
  → Comprar al primer "Buy" del PineScript
  → Sizing: T1, habilitar T2/T3 con condición de precio decreciente

  [PRIORIDAD 2 — Confianza ALTA] 📈 ID: Aa22
  (ema50_angle >= 0)    ← EMA50 ascendente (ángulo positivo)
  AND (ema4 precio >= basis)   ← EMA50 sobre la VWMA
  → Tendencia macro y local alineadas
  → Sizing: T1

  [PRIORIDAD 3 — Confianza MEDIA] 📈 ID: Aa23
  (ema9_angle  >= 0)    ← EMA9 ascendente
  AND (ema50_angle >= 0)    ← EMA50 ascendente
  AND (adx >= adx_min del régimen)
  → Sizing: T1

  [PRIORIDAD 4 — Confianza MEDIA-BAJA] 🔍 ID: Aa21
  (ema20_angle >= 0)
  AND (adx < 20)
  AND (zona_fibonacci ENTRE -2 Y +2)   ← precio cerca del basis
  AND (close <= basis × 1.005)         ← no entrar lejos del basis
  AND (solo régimen bajo_riesgo)
  → Sizing: solo T1
```

### 6.4 Condiciones de entrada SHORT

```
══════════════════════════════════════════════════════════════════
B. COMPRAR SHORT — señal "Sell" del PineScript (Nivel -1 o -2)
══════════════════════════════════════════════════════════════════
⚠️ En macro alcista (EMA50 > EMA200): aplicar RR mínimo forzado 3.0
   y solo T1 independientemente del régimen.

RAMA B1 — EMA50 < EMA200 (macro bajista → shorts favorecidos)

  [PRIORIDAD 1 — Confianza ALTA] ⚡ ID: Bb12
  EMA50 cruza hacia ABAJO el basis (VWMA)
  → Comprar SHORT al primer "Sell" del PineScript
  → Sizing: T1 × sizing_multiplier(confluence_score)

  [PRIORIDAD 2 — Confianza ALTA] 📉 ID: Bb13
  (ema4 precio <= basis)
  AND (adx < 20)
  AND (ema20_phase IN ['flat', 'nivel_1_short'])
  AND (di_cross_bearish == True)
  AND (ema20_angle <= 0)
  → Distribución temprana en consolidación
  → Sizing: T1

  [PRIORIDAD 3 — Confianza MEDIA] 💪 ID: Bb11
  (ema20_angle <= 0)
  AND (adx > 40)
  AND (ema20_phase == 'nivel_2_short')
  AND (minus_di > plus_di + 5)   ← margen mínimo de 5 puntos
  → Solo régimen riesgo_medio o bajo_riesgo
  → Sizing: T1 + habilitar T2

RAMA B2 — EMA50 > EMA200 (macro alcista → contra-tendencia)

  [PRIORIDAD 1 — Confianza ALTA] ⚡ ID: Bb22
  (high cruzó upper_6 en últimas 2 velas)
  AND (adx > 40)
  AND (ema20_phase == 'nivel_2_long')
  AND (ema50_angle <= 0)          ← EMA50 girando negativo
  AND confirmación de reversal:
      is_gravestone
      OR (is_red_candle AND high_in_upper_6_zone)
      OR high_lower_than_prev
  → Sizing: solo T1, RR mínimo forzado 3.0

  [PRIORIDAD 2 — Confianza ALTA] ⚡ ID: Bb23
  EMA50 cruza hacia ABAJO el basis (VWMA)
  AND (ema20_angle <= 0)
  → Comprar SHORT al primer "Sell" del PineScript
  → Sizing: T1

  [PRIORIDAD 3 — Confianza MEDIA] 💪 ID: Bb21
  (ema20_angle <= 0)
  AND (adx > 40)
  AND (ema20_phase == 'nivel_2_short')
  AND (minus_di > plus_di + 10)  ← margen mínimo de 10 puntos
  AND (solo régimen bajo_riesgo)
  → Sizing: T1, RR mínimo 3.0
```

---

## 7. GESTIÓN DE CAPITAL Y SIZING

### 7.1 Parámetros configurables en panel

```
MÓDULO CONFIGURACIÓN — Sección Capital
═══════════════════════════════════════════════════════
Capital Total:          [ $500  ]  (editable: cualquier monto)
% para Trading:         [  20%  ]  (editable: 5% - 100%)
─────────────────────────────────────────────────────
Capital Operativo:      $90      (= Capital × % × 0.90)
Buffer seguridad (10%): $10      (fees/slippage, fijo)
─────────────────────────────────────────────────────
TRADES HABILITADOS AUTOMÁTICAMENTE según capital operativo:
  < $30      → Solo 1 trade
  $30 - $60  → Hasta 2 trades
  $60 - $150 → Hasta 3 trades  ← caso $500 × 20% = $90
  $150 - $300→ Hasta 4 trades
  > $300     → Hasta 5 trades

Distribución por trade (editable, suma debe = 100%):
  3 trades: T1:[20%] T2:[30%] T3:[50%]
  5 trades: T1:[10%] T2:[15%] T3:[20%] T4:[25%] T5:[30%]
═══════════════════════════════════════════════════════
NOTA: El sistema valida que cada trade sea >= $15 (mínimo Binance).
Si no alcanza el mínimo, bloquea ese trade y notifica en panel.
```

### 7.2 Función de sizing con validaciones

```python
BINANCE_MIN_ORDER = 15.0  # USD

def calculate_position_sizes(
    capital_operativo: float,
    n_trades_config:   int,
    regime:            str,
    confluence_score:  int   # 1, 2 o 3 TFs alineados
) -> list[dict]:
    """
    Calcula el monto en USD para cada entrada.

    Ajuste por confluencia:
      3 TFs alineados → sizing completo (×1.00)
      2 TFs alineados → sizing reducido (×0.85)
      1 TF alineado   → sizing reducido (×0.70)
    """
    max_by_regime = {'alto_riesgo': 1, 'riesgo_medio': 3, 'bajo_riesgo': 5}
    effective_n   = min(n_trades_config, max_by_regime[regime])

    distributions = {
        1: [1.00],
        2: [0.40, 0.60],
        3: [0.20, 0.30, 0.50],
        4: [0.15, 0.20, 0.30, 0.35],
        5: [0.10, 0.15, 0.20, 0.25, 0.30],
    }

    sizing_mult = {1: 0.70, 2: 0.85, 3: 1.00}[confluence_score]
    dist        = distributions[effective_n]
    result      = []

    for i, pct in enumerate(dist, start=1):
        usd = round(capital_operativo * pct * sizing_mult, 2)
        if usd < BINANCE_MIN_ORDER:
            # Notificar pero no incluir este trade
            continue
        result.append({
            'trade_n':           i,
            'usd':               usd,
            'pct':               round(pct * 100, 1),
            'price_cond_long':   None if i == 1 else f'close < trade_{i-1}_price',
            'price_cond_short':  None if i == 1 else f'close > trade_{i-1}_price',
        })

    return result
```

---

## 8. GESTIÓN DE POSICIÓN

### 8.1 Precio promedio ponderado y SL dinámico

```python
@dataclass
class PositionEntry:
    trade_n:     int
    price:       float
    usd_amount:  float
    timestamp:   datetime
    rule_code:   str       # Aa13, Bb22, etc.

@dataclass
class Position:
    symbol:      str
    side:        str       # 'long' | 'short'
    entries:     list      # lista de PositionEntry
    sl_price:    float
    tp_upper5:   float     # upper_5 o lower_5 (cierre parcial)
    tp_upper6:   float     # upper_6 o lower_6 (cierre total)
    is_open:     bool = True

    @property
    def avg_entry_price(self) -> float:
        total_usd   = sum(e.usd_amount for e in self.entries)
        weighted    = sum(e.price * e.usd_amount for e in self.entries)
        return weighted / total_usd if total_usd > 0 else 0.0

    @property
    def total_usd(self) -> float:
        return sum(e.usd_amount for e in self.entries)

    def update_sl_after_new_entry(self, atr: float, atr_mult: float):
        """
        Recalcular SL después de cada nueva entrada.
        Usa el precio promedio ponderado acumulado, NO el precio de T1.
        """
        avg = self.avg_entry_price
        if self.side == 'long':
            self.sl_price = avg - (atr * atr_mult)
        else:
            self.sl_price = avg + (atr * atr_mult)

    def check_breakeven(self, current_price: float, fee_pct: float = 0.001) -> bool:
        """
        Mover SL a break-even cuando el trade alcanza RR 1:1.
        Break-even = precio_promedio + buffer de fees.
        """
        avg       = self.avg_entry_price
        risk      = abs(avg - self.sl_price)
        be_target = avg + risk if self.side == 'long' else avg - risk

        if self.side == 'long'  and current_price >= be_target:
            self.sl_price = avg * (1 + fee_pct)  # break-even + buffer
            return True
        if self.side == 'short' and current_price <= be_target:
            self.sl_price = avg * (1 - fee_pct)
            return True
        return False
```

### 8.2 Take Profit con confirmación de volumen y velas

```python
def evaluate_take_profit_full(
    df:       pd.DataFrame,
    position: Position,
    regime:   str
) -> dict:
    """
    Lógica de cierre completa según EMA50 vs EMA200.

    EMA50 > EMA200 (modo tendencia):
      Cerrar parcialmente en upper_5/5 + cerrar total en Nivel 3 / upper_6

    EMA50 < EMA200 (modo defensivo):
      Cerrar en cuanto llegue a upper_5 o upper_6 sin esperar Nivel 3
    """
    last          = df.iloc[-1]
    current_price = float(last['close'])
    ema50_val     = float(last['ema4'])
    ema200_val    = float(last['ema5'])
    trend_mode    = ema50_val > ema200_val  # True = modo tendencia

    if position.side == 'long':
        in_tp_partial = current_price >= position.tp_upper5
        in_tp_full    = current_price >= position.tp_upper6

        # Modo tendencia: esperar Nivel 3 + confirmación
        if trend_mode:
            nivel3_confirmed = (
                last['ema20_phase'] == 'nivel_3_long' and
                last['vol_decreasing'] and (
                    last['is_gravestone'] or
                    last['high_lower_than_prev'] or
                    (last['is_red_candle'] and in_tp_full)
                )
            )
            return {
                'close_partial': in_tp_partial,
                'close_full':    in_tp_full and nivel3_confirmed,
                'reason':        'Nivel 3 + agotamiento volumen + vela reversal' if nivel3_confirmed else '',
                'mode':          'trend',
            }
        else:
            # Modo defensivo: cerrar en cuanto llegue a upper_5 o upper_6
            return {
                'close_partial': in_tp_partial,
                'close_full':    in_tp_full,
                'reason':        'Modo defensivo EMA50 < EMA200',
                'mode':          'defensive',
            }

    else:  # short
        in_tp_partial = current_price <= position.tp_upper5  # lower_5
        in_tp_full    = current_price <= position.tp_upper6  # lower_6

        if trend_mode:
            nivel3_confirmed = (
                last['ema20_phase'] == 'nivel_3_short' and
                last['vol_increasing'] and (
                    last['is_dragonfly'] or
                    last['low_higher_than_prev'] or
                    (last['is_green_candle'] and in_tp_full)
                )
            )
            return {
                'close_partial': in_tp_partial,
                'close_full':    in_tp_full and nivel3_confirmed,
                'reason':        'Nivel -3 + aumento volumen + vela reversal' if nivel3_confirmed else '',
                'mode':          'trend',
            }
        else:
            return {
                'close_partial': in_tp_partial,
                'close_full':    in_tp_full,
                'reason':        'Modo defensivo EMA50 < EMA200',
                'mode':          'defensive',
            }
```

### 8.3 Cierre parcial proporcional a las entradas

```python
def calculate_partial_close_sizes(position: Position) -> dict:
    """
    En upper_5 (partial): cerrar los trades más pequeños (los primeros).
    En upper_6 / Nivel 3 (full): cerrar los trades más grandes (el resto).

    Con 3 entradas:
      Partial (upper_5): cerrar T1 (20%) + T2 (30%) = 50% de la posición
      Full (upper_6):    cerrar T3 (50%) = el mayor capital
      → T3 siempre viaja al extremo más rentable.

    Con 1 entrada:
      Partial (upper_5): cerrar 40%
      Full (upper_6):    cerrar 60%
    """
    n = len(position.entries)
    if n == 1:
        total = position.entries[0].usd_amount
        return {
            'partial_usd': round(total * 0.40, 2),
            'full_usd':    round(total * 0.60, 2),
        }

    # Ordenar por monto ascendente: los más pequeños se cierran primero
    sorted_entries  = sorted(position.entries, key=lambda e: e.usd_amount)
    half            = len(sorted_entries) // 2 + (1 if len(sorted_entries) % 2 else 0)
    partial_entries = sorted_entries[:half]
    full_entries    = sorted_entries[half:]

    return {
        'partial_usd':      sum(e.usd_amount for e in partial_entries),
        'full_usd':         sum(e.usd_amount for e in full_entries),
        'partial_trades':   [e.trade_n for e in partial_entries],
        'full_trades':      [e.trade_n for e in full_entries],
    }
```

### 8.4 Flujo de 2 pasos (cerrar → abrir)

```python
def process_signal_two_steps(
    new_signal:    str,   # 'long' | 'short'
    current_price: float,
    symbol:        str,
    timestamp:     datetime,
    open_position: Position | None,
    rr_valid:      bool,
    sizes:         list[dict]
) -> list[dict]:
    """
    Regla: si hay posición contraria abierta, SIEMPRE cerrar primero.
    Solo abrir nueva posición si RR es válido.
    Si RR no válido: cerrar de todas formas, quedar flat.
    """
    orders = []

    # PASO 1: Cerrar posición contraria si existe
    if open_position and open_position.side != new_signal:
        orders.append({
            'step':        1,
            'action':      'close',
            'side':        open_position.side,
            'symbol':      symbol,
            'price':       current_price,
            'avg_entry':   open_position.avg_entry_price,
            'reason':      f'Señal {new_signal.upper()} opuesta — cerrar {open_position.side.upper()}',
            'timestamp':   timestamp.isoformat(),
        })

    # PASO 2: Abrir nueva posición (solo si RR válido)
    if rr_valid:
        orders.append({
            'step':        len(orders) + 1,
            'action':      'open',
            'side':        new_signal,
            'symbol':      symbol,
            'price':       current_price,
            'sizes':       sizes,
            'timestamp':   timestamp.isoformat(),
        })
    else:
        # Quedar flat: registrar el veto por RR
        orders.append({
            'step':        len(orders) + 1,
            'action':      'flat',
            'reason':      f'RR insuficiente para abrir {new_signal.upper()}. Sistema en espera.',
            'timestamp':   timestamp.isoformat(),
        })

    return orders
```

---

## 9. PROTECCIONES DE RIESGO

### 9.1 Circuit breaker

```python
# Configurable en panel:
CIRCUIT_BREAKER = {
    'max_daily_loss_pct':  5.0,   # % del capital total
    'max_trade_loss_pct':  2.0,   # % del capital total por trade
    # Ambos editables en Configuración
}

def check_circuit_breaker(
    daily_pnl_usd:   float,
    capital_total:   float,
    config:          dict
) -> dict:
    daily_loss_pct = abs(min(daily_pnl_usd, 0)) / capital_total * 100

    triggered = daily_loss_pct >= config['max_daily_loss_pct']
    return {
        'triggered':       triggered,
        'daily_loss_pct':  round(daily_loss_pct, 2),
        'daily_loss_usd':  round(abs(min(daily_pnl_usd, 0)), 2),
        'reset_at':        '00:00 UTC del día siguiente' if triggered else None,
    }
```

### 9.2 Cooldown post-SL / post-TP

```python
COOLDOWN_CONFIG = {
    'post_sl_bars': 3,  # velas del timeframe activo — editable
    'post_tp_bars': 1,  # editable
}

# En Supabase: tabla cooldowns
# { symbol, timeframe, cooldown_type, triggered_at, expires_at, active }
```

### 9.3 Tiempo máximo de posición abierta

```python
MAX_HOLDING_BARS = {
    '15m': 48,   # 12 horas — editable en Configuración
    '30m': 48,   # 24 horas
    '45m': 32,   # 24 horas
    '4h':  30,   # 5 días
    '1d':  14,   # 2 semanas
    '1w':  8,    # 2 meses
}

def check_max_holding(position: Position,
                       current_bar: int,
                       entry_bar:   int,
                       timeframe:   str,
                       current_price: float) -> dict:
    bars_held = current_bar - entry_bar
    max_bars  = MAX_HOLDING_BARS.get(timeframe, 48)

    if bars_held >= max_bars:
        in_profit = (
            (position.side == 'long'  and current_price > position.avg_entry_price) or
            (position.side == 'short' and current_price < position.avg_entry_price)
        )
        return {
            'expired':   True,
            'action':    'partial_close_and_breakeven' if in_profit else 'alert_manual',
            'bars_held': bars_held,
        }
    return {'expired': False, 'bars_held': bars_held}
```

### 9.4 Filtro de correlación multi-símbolo

```python
def check_correlation_filter(
    symbol_new:    str,
    direction_new: str,
    open_positions: list,
    df_dict:        dict,   # {symbol: DataFrame}
    max_correlation: float = 0.80,
    window: int = 20
) -> dict:
    """
    Si correlación entre símbolo nuevo y símbolo con posición abierta
    en la MISMA dirección > 0.80: bloquear entrada.
    Priorizar el que tiene mayor ADX + menor zona Fibonacci.
    """
    for pos in open_positions:
        if pos.side != direction_new:
            continue

        # Calcular correlación rolling 20 barras
        returns_new = df_dict[symbol_new]['close'].pct_change().tail(window)
        returns_pos = df_dict[pos.symbol]['close'].pct_change().tail(window)
        corr        = returns_new.corr(returns_pos)

        if corr > max_correlation:
            return {
                'blocked':     True,
                'reason':      f'Correlación {corr:.2f} con {pos.symbol} ya abierto en {pos.side}',
                'correlation': round(corr, 3),
            }

    return {'blocked': False}
```

### 9.5 Precio de liquidación (Futuros)

```python
def calculate_liquidation_price(
    entry_price:        float,
    leverage:           int,
    side:               str,
    maintenance_margin: float = 0.005  # 0.5% Binance default
) -> dict:
    """
    CRÍTICO: el SL calculado por ATR DEBE ser menos extremo que el
    precio de liquidación. Si el ATR genera SL más allá de la liquidación:
      a) Reducir apalancamiento automáticamente, o
      b) Bloquear la entrada y notificar
    """
    if side == 'long':
        liq = entry_price * (1 - (1/leverage) + maintenance_margin)
    else:
        liq = entry_price * (1 + (1/leverage) - maintenance_margin)

    distance_pct = abs(entry_price - liq) / entry_price * 100

    return {
        'liquidation_price': round(liq, 4),
        'distance_pct':      round(distance_pct, 2),
        'leverage':          leverage,
    }
```

### 9.6 Funding Rate (Futuros)

```python
async def get_funding_rate(symbol: str, binance_client) -> dict:
    """
    Leer en ciclo de 5m. Binance cobra cada 8 horas.
    Proyectar costo según holding period esperado.
    """
    data         = await binance_client.get_funding_rate(symbol)
    rate         = float(data['lastFundingRate'])
    next_funding = data['nextFundingTime']

    # Proyección para 24 horas (3 pagos)
    projected_cost_24h = abs(rate) * 3

    return {
        'rate':                 rate,
        'next_funding_time':    next_funding,
        'projected_cost_24h':   round(projected_cost_24h * 100, 4),  # en %
        'favorable_for_long':   rate < 0,   # negativo = vendedores pagan
        'favorable_for_short':  rate > 0,
    }
```

### 9.7 Fees integrados en el RR

```python
def calculate_real_rr(
    entry:    float,
    tp:       float,
    sl:       float,
    fee_pct:  float = 0.001   # 0.1% Binance default
) -> float:
    """RR ajustado por fees round-trip."""
    eff_entry = entry * (1 + fee_pct)
    eff_tp    = tp    * (1 - fee_pct)
    eff_sl    = sl    * (1 - fee_pct)
    return round((eff_tp - eff_entry) / (eff_entry - eff_sl), 2)
```

### 9.8 Health check de símbolo

```python
async def check_symbol_health(
    symbol:         str,
    binance_client,
    min_volume_24h: float = 1_000_000,  # USD — configurable
    max_spread_pct: float = 0.15        # % — configurable
) -> dict:
    """
    Verificar antes de abrir cualquier posición:
    1. Volumen 24h suficiente
    2. Spread bid/ask aceptable
    3. Símbolo no en modo "only reduce"
    """
    book    = await binance_client.get_order_book(symbol, limit=5)
    ticker  = await binance_client.get_24hr_ticker(symbol)

    best_bid = float(book['bids'][0][0])
    best_ask = float(book['asks'][0][0])
    spread   = (best_ask - best_bid) / best_bid * 100
    vol_24h  = float(ticker['quoteVolume'])

    return {
        'healthy':       vol_24h > min_volume_24h and spread < max_spread_pct,
        'volume_24h':    round(vol_24h, 0),
        'spread_pct':    round(spread, 4),
        'volume_ok':     vol_24h > min_volume_24h,
        'spread_ok':     spread < max_spread_pct,
    }
```

---

## 10. INFRAESTRUCTURA Y DATAPROVIDER

### 10.1 Abstracción DataProvider

```python
from abc import ABC, abstractmethod

class DataProvider(ABC):
    """
    Interfaz común para todos los mercados.
    La lógica de trading NUNCA llama directamente a Binance/OANDA.
    Siempre usa este contrato.
    """
    @abstractmethod
    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        pass

    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        pass

    @abstractmethod
    async def place_order(self, symbol: str, side: str,
                          size: float, price: float = None,
                          order_type: str = 'LIMIT') -> dict:
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> dict:
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        pass


class BinanceCryptoProvider(DataProvider):
    """
    Implementación para Crypto SPOT y Crypto FUTURES.
    Sprint 1 — único proveedor activo.
    """
    def __init__(self, api_key: str, api_secret: str, market: str = 'futures'):
        # market: 'spot' | 'futures'
        self.market = market
        # Inicializar cliente Binance aquí
        pass
    # ... implementar métodos abstractos


# Sprint 3 — estructura para Forex (referencia):
# class OandaForexProvider(DataProvider): ...
```

### 10.2 Selección de mercado en el sistema

```
CONFIGURACIÓN — Sección Mercado
══════════════════════════════════════════════════════
  Modo de mercado activo:
    ○ Crypto SPOT
    ● Crypto FUTURES  ← seleccionado
    ○ Forex SPOT      (Sprint 3)
    ○ Forex FUTURES   (Sprint 3)

  Nivel de apalancamiento (solo Futuros): [ 5x ]
    Rango: 1x - 20x (editable)
    ADVERTENCIA: sistema calcula precio de liquidación automáticamente
    y bloquea entrada si SL supera precio de liquidación.

  Símbolos disponibles — SPOT:
    [+ Agregar] BTC/USDT | ETH/USDT | SOL/USDT | ADA/USDT | [···]

  Símbolos disponibles — FUTUROS:
    [+ Agregar] BTC/USDT | ETH/USDT | SOL/USDT | ADA/USDT | [···]

  Símbolos activos (operando ahora):
    [☑ BTC/USDT] [☑ ETH/USDT] [☑ SOL/USDT] [☑ ADA/USDT]
══════════════════════════════════════════════════════
NOTA PARA ANTIGRAVITY: todos los datos OHLCV, precios y órdenes
provienen del mercado seleccionado. El cambio de SPOT a FUTURES
cambia el endpoint de Binance utilizado en BinanceCryptoProvider.
```

### 10.3 Reconciliación bot vs exchange

```python
async def reconcile_positions(
    position_manager: dict,  # estado en Supabase
    binance_client,
    symbols: list[str]
) -> list[dict]:
    """
    Ejecutar cada 3 ciclos de 15m (= 45 minutos).
    Compara el estado del bot con las posiciones reales en Binance.
    Supabase es actualizado con el estado real (Binance = source of truth).
    """
    discrepancies = []

    for symbol in symbols:
        real_pos  = await binance_client.get_position(symbol)
        bot_state = position_manager.get(symbol)

        if real_pos != bot_state:
            # Actualizar Supabase con estado real
            await supabase.table('positions').upsert({
                'symbol':    symbol,
                'state':     real_pos,
                'source':    'reconciliation',
                'updated_at': datetime.utcnow().isoformat()
            }).execute()

            discrepancies.append({
                'symbol':     symbol,
                'bot_state':  bot_state,
                'real_state': real_pos,
                'action':     'supabase_updated'
            })

            # Log y notificación Telegram
            await log_reconciliation(symbol, bot_state, real_pos)

    return discrepancies
```

### 10.4 Rate Limiting

```python
class RateLimiter:
    """Token bucket: usar solo 50% del límite de Binance (600/min)."""
    def __init__(self, max_calls_per_minute: int = 600):
        self.max_calls = max_calls_per_minute
        self.tokens    = max_calls_per_minute
        self.last_refill = time.time()

    def can_proceed(self) -> bool:
        self._refill()
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

    def _refill(self):
        now     = time.time()
        elapsed = now - self.last_refill
        refill  = elapsed * (self.max_calls / 60)
        self.tokens = min(self.max_calls, self.tokens + refill)
        self.last_refill = now
```

### 10.5 Gestión de API Keys — seguridad

```
REGLAS PARA ANTIGRAVITY:

✓ Las API keys se guardan en variables de entorno de Render (worker Python)
✓ Nunca en código fuente, nunca en Supabase sin encriptar
✓ El frontend Next.js envía las keys por HTTPS al backend UNA sola vez
✓ El backend las guarda via Render API — nunca las devuelve al frontend
✓ El panel muestra solo: "API Key: ****...last4chars"

Permisos mínimos en Binance:
  ✓ Enable Reading
  ✓ Enable Spot & Margin Trading
  ✓ Enable Futures
  ✗ Enable Withdrawals (NUNCA)
  ✗ Enable Universal Transfer (NUNCA)

IP Whitelist: agregar solo la IP del servidor Render del worker.
```

### 10.6 Período de calentamiento

```python
WARMUP_REQUIRED_BARS = 200  # EMA200 + Fibonacci BB (el más largo)

async def initialize_symbol(symbol: str, timeframe: str,
                              provider: DataProvider,
                              supabase_client) -> dict:
    """
    Al agregar un nuevo símbolo, descargar las últimas 200+ velas históricas.
    Binance permite hasta 1000 velas por llamada REST.
    No esperar que pasen en tiempo real.
    """
    df = await provider.get_ohlcv(symbol, timeframe, limit=500)

    if len(df) < WARMUP_REQUIRED_BARS:
        return {'status': 'warming_up', 'progress': f'{len(df)}/{WARMUP_REQUIRED_BARS}'}

    # Calcular todos los indicadores con datos históricos
    df = fibonacci_bollinger(df)
    df = calculate_macd_4c(df)
    df = calculate_emas(df)
    df = calculate_adx(df)
    df = classify_ema20_phase(df)

    # Guardar en Supabase
    await save_ohlcv_to_supabase(df, symbol, timeframe, supabase_client)

    return {'status': 'active', 'bars_loaded': len(df)}
```

### 10.7 Slippage Tracking

```python
# Registrar en cada trade ejecutado:
# {
#   trade_id, symbol, signal_price, execution_price,
#   slippage_pct, order_type, timestamp
# }
# Dashboard: slippage promedio por símbolo y tipo de orden
```

---

## 11. FRONTEND — NEXT.JS / REACT

### 11.1 Toggle Paper Trading / Modo Real

```
AL INICIAR EL SISTEMA (login):
  ┌──────────────────────────────────────────────────────┐
  │  eTrade                                              │
  │  ─────────────────────────────────────────────────  │
  │  Usuario: [           ]  Contraseña: [           ]  │
  │                                                      │
  │  Modo de operación:                                  │
  │    ○ 📄 PAPER TRADING (simulación con precios reales)│
  │    ○ 🔴 MODO REAL     (ejecución real en Binance)   │
  │                                                      │
  │  ⚠️ En MODO REAL las órdenes se ejecutan realmente.  │
  │     Asegúrate de tener las API keys configuradas.    │
  │                                                      │
  │                              [Ingresar al sistema]   │
  └──────────────────────────────────────────────────────┘

Paper Trading:
  → Usa precios reales de Binance en tiempo real
  → NO ejecuta órdenes reales
  → Simula fills al precio de cierre de vela
  → Registra todos los trades simulados en Supabase (tabla: paper_trades)
  → Banner permanente en el panel: "📄 MODO PAPER TRADING ACTIVO"
```

### 11.2 Panel de Configuración completo

```
MÓDULO CONFIGURACIÓN
═══════════════════════════════════════════════════════════════
SECCIÓN 1 — CAPITAL Y SIZING
  Capital Total:          [ $500  ]
  % para Trading:         [  20%  ]
  Capital Operativo:      $90      (calculado)
  Trades habilitados:     HASTA 3  (calculado por capital)

  Distribución de trades (editable, suma = 100%):
    T1: [ 20% ]  T2: [ 30% ]  T3: [ 50% ]

SECCIÓN 2 — PARÁMETROS POR RÉGIMEN (tabla editable)
  ┌──────────────────────┬─────────┬──────────┬──────────┐
  │ Parámetro            │ 🔴 Alto │ 🟡 Medio │ 🟢 Bajo  │
  ├──────────────────────┼─────────┼──────────┼──────────┤
  │ MTF Threshold        │ [0.80]  │ [0.65]   │ [0.50]   │
  │ Max Trades           │ [1]     │ [3]      │ [5]      │
  │ ATR Multiplier SL    │ [2.5]   │ [2.0]    │ [1.5]    │
  │ RR Mínimo            │ [3.0]   │ [2.5]    │ [2.0]    │
  │ ADX Mínimo           │ [30]    │ [20]     │ [15]     │
  │ Nivel mín. entrada   │ [2]     │ [1]      │ [1]      │
  │ DI Cross requerido   │ [SÍ]    │ [SÍ]     │ [NO]     │
  │ EMA20 flat_pct       │ [25]    │ [20]     │ [15]     │
  │ EMA20 peak_pct       │ [75]    │ [80]     │ [85]     │
  └──────────────────────┴─────────┴──────────┴──────────┘

SECCIÓN 3 — TIMEFRAMES Y HOLDING
  Max velas por TF (editable):
    15m:[48] 30m:[48] 45m:[32] 4h:[30] 1d:[14] 1w:[8]
  Señal PineScript expira en: [3] velas

SECCIÓN 4 — PROTECCIONES
  Pérdida máxima diaria:    [ 5%  ] del capital total
  Pérdida máxima por trade: [ 2%  ] del capital total
  Cooldown post-SL:         [ 3   ] velas
  Cooldown post-TP:         [ 1   ] vela
  Correlación máxima:       [0.80 ]
  Vol mínimo entrada:       [ 70% ] del vol_ema

SECCIÓN 5 — ÓRDENES
  Tipo de orden entrada:    [ Limit | Market ]  (default: Limit)
  Timeout orden límite:     [ 2   ] velas
  Gap stop-limit SL:        [0.10 ] %
  Fee estimado:             [0.10 ] %

SECCIÓN 6 — EMERGENCIA
  Activar monitor intra-ciclo: [SÍ]
  ATR multiplicador alerta:    [2.0]
  Acción:  ○ Pausar  ● Alertar  ○ Cerrar todo

SECCIÓN 7 — MERCADO Y SÍMBOLOS
  [ver sección 10.2]

SECCIÓN 8 — IA DE VELAS
  Activar interpretación IA:  [SÍ]
  Modo Sprint 1:              [Informativa] (no bloquea entradas)

SECCIÓN 9 — TELEGRAM
  Bot Token:     [**************]
  Chat ID:       [**************]
  [Probar conexión]

SECCIÓN 10 — BACKUP
  [📥 Exportar configuración]  [📤 Importar configuración]  [↺ Restaurar defaults]
  Últimas 10 snapshots disponibles para restaurar.

[⚡ Reglas de Entrada]  ← botón que abre ventana flotante Rule Engine
═══════════════════════════════════════════════════════════════
```

### 11.3 Dashboard principal — Supabase Realtime

```typescript
// Suscripción a cambios en tiempo real (NO polling)
useEffect(() => {
  const subscription = supabase
    .channel('trading_updates')
    .on('postgres_changes',
      { event: '*', schema: 'public', table: 'positions' },
      (payload) => updatePositions(payload.new)
    )
    .on('postgres_changes',
      { event: '*', schema: 'public', table: 'signals' },
      (payload) => updateSignals(payload.new)
    )
    .on('postgres_changes',
      { event: '*', schema: 'public', table: 'market_regime' },
      (payload) => updateRegime(payload.new)
    )
    .subscribe()
  return () => subscription.unsubscribe()
}, [])
```

**Layout del dashboard:**
```
┌──────────────────────────────────────────────────────────────────┐
│ eTrade  📄 PAPER TRADING          🟡 Riesgo Medio  Score: 48.2  │
├──────────────────────────────────────────────────────────────────┤
│ [BTC/USDT] [ETH/USDT] [SOL/USDT] [ADA/USDT]                    │
│ [15m] [30m] [45m] [4h] [1D] [1W]                                │
├─────────────────────────────────┬────────────────────────────────┤
│ FIBONACCI BB — BTC/USDT 15m     │ POSICIÓN ACTUAL               │
│                                  │  LONG × 2 trades              │
│ 🎯 TP AGR  upper_6: $69,500     │  Entrada prom.: $64,200       │
│ TP CONS   upper_5: $68,100 ←TP  │  T1: $18 @ $65,000           │
│ ─────── basis: $65,000 ──────   │  T2: $27 @ $63,400           │
│ TP SHORT  lower_5: $61,900      │  SL actual: $61,850           │
│ 🎯 TP AGR  lower_6: $60,500     │  Break-even: NO               │
│                                  │  P&L actual: +$2.40 (+2.7%)  │
│ ZONA ACTUAL: +2 ↑               │  Holding: 8/48 velas          │
│ Precio: $65,800                  │                               │
├─────────────────────────────────┤  [Cierre Manual]              │
│ SEÑALES                          │                               │
│ Regla activa: Aa22 ⚡           ├────────────────────────────────┤
│ EMA20 fase: nivel_2_long        │ IA VELAS                      │
│ ADX: 32.4  +DI: 28  -DI: 18    │ 📊 Doji en Upper_2            │
│ Confluencia: 3/3 TFs ✓         │ Conf: 82%  Indecisión         │
│ ema50_angle: +2.1° ascendente   │ "Mercado muestra pausa tras   │
│ Vol: 125K vs EMA 180K ↓        │  impulso. Posible consolidac." │
│                                  │ Sistema: ⏳ Informativa        │
├─────────────────────────────────┴────────────────────────────────┤
│ RÉGIMEN: 🟡 Riesgo Medio │ ATR: 48° percentil │ Vol ratio: 0.69 │
│ Emergencia: OFF │ Circuit breaker: OFF │ Cooldown: OFF           │
├──────────────────────────────────────────────────────────────────┤
│ ÚLTIMOS TRADES             Win:3  Loss:1  P&L hoy: +$6.20       │
│ LONG BTC Aa22 TP +$4.20 (+23%) upper_5 ✓                       │
│ SHORT ETH Bb12 SL -$1.80 (-10%) cooldown 3v                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 12. NOTIFICACIONES TELEGRAM

```python
TELEGRAM_EVENTS = {
    'trade_opened': '🟢 {side} {symbol} @ ${price:.2f} | ${usd} | {rule} | {regime}',
    'tp_partial':   '📈 TP PARCIAL {symbol} +${pnl:.2f} ({pnl_pct:.1f}%) | upper_5 | Vol: ✓',
    'tp_full':      '🏆 TP TOTAL {symbol} +${pnl:.2f} ({pnl_pct:.1f}%) | {level} | Nivel 3 ✓',
    'sl_hit':       '🔴 SL {symbol} -${pnl:.2f} ({pnl_pct:.1f}%) | Cooldown {bars}v',
    'emergency':    '🚨 EMERGENCIA {symbol} | ATR {ratio:.1f}x promedio | Entradas pausadas',
    'circuit_break':'⚡ CIRCUIT BREAKER | Pérdida diaria {pct:.1f}% | Sistema pausado hasta 00:00 UTC',
    'reconcile':    '⚠️ DISCREPANCIA {symbol} | Bot: {bot} | Binance: {real} | Corregido',
    'daily_summary':'📊 RESUMEN {date} | Trades:{n} W:{w} L:{l} | P&L:${pnl:.2f} | Capital:${cap:.2f}',
}
```

---

## 13. PAPER TRADING MODE

```
COMPORTAMIENTO EN PAPER TRADING:
  1. Todas las fases del pipeline se ejecutan normalmente
  2. Al llegar a FASE 5 (ejecutar orden):
     → En lugar de llamar a Binance API place_order()
     → Simular fill al precio de cierre de la vela actual
     → Registrar en tabla paper_trades con campo mode='paper'
  3. P&L se calcula igual que en modo real
  4. Todos los indicadores (SL, TP, break-even) se monitorean igual
  5. Telegram notifica igual (con prefijo "[PAPER]")
  6. Dashboard muestra banner permanente: "📄 MODO PAPER TRADING"

TABLA SUPABASE: paper_trades
  id, symbol, side, entry_price, sl_price, tp_price,
  exit_price, exit_reason, pnl_usd, pnl_pct,
  rule_code, regime, ema20_phase, adx_value,
  confluence_score, ai_recommendation, ai_agreed,
  opened_at, closed_at, bars_held, mode

ESTE REGISTRO ES EL INPUT DEL DASHBOARD DE PERFORMANCE (Sprint 2).
Win rate por regla, RR promedio real, mejor condición, etc.
```

---

## 14. RETENCIÓN Y LIMPIEZA DE DATOS

```python
# Política de retención por timeframe:
RETENTION_POLICY = {
    '5m':  20,    # días — alertas de emergencia
    '15m': 60,    # días — señales principales
    '30m': 90,    # días
    '45m': 120,   # días
    '4h':  365,   # días — 1 año
    '1d':  1095,  # días — 3 años (cubrir EMA200)
    '1w':  2190,  # días — 6 años (cubrir EMA200 semanal)
}

# Worker de limpieza: ejecutar 1 vez por día a las 00:00 UTC
async def cleanup_old_ohlcv():
    for timeframe, days in RETENTION_POLICY.items():
        cutoff = datetime.utcnow() - timedelta(days=days)
        await supabase.table('ohlcv_data')\
            .delete()\
            .eq('timeframe', timeframe)\
            .lt('timestamp', cutoff.isoformat())\
            .execute()

# Estimación de almacenamiento con 4 símbolos:
# Total: ~21 MB → muy por debajo del límite free de Supabase (500 MB)
```

---

## 15. ENTREGABLES Y CRITERIOS DE ACEPTACIÓN — SPRINT 1

### 15.1 Entregables por responsable

| # | Módulo | Archivo / Endpoint | Resp. |
|---|--------|--------------------|-------|
| 1 | Fibonacci BB core | `fibonacci_bb.py` | Backend |
| 2 | MACD 4C + EMAs + EMA20 phases | `indicators.py` | Backend |
| 3 | ADX + DI | `adx.py` | Backend |
| 4 | Detección volumen + velas reversal | `volume_candles.py` | Backend |
| 5 | Régimen dinámico | `market_regime.py` | Backend |
| 6 | Rule Engine evaluator | `rule_engine.py` | Backend |
| 7 | Gestión de posición + sizing | `position_manager.py` | Backend |
| 8 | Protecciones (circuit breaker, cooldown, correlation) | `risk_controls.py` | Backend |
| 9 | DataProvider Binance (SPOT + Futures) | `providers/binance.py` | Backend |
| 10 | WebSocket Manager | `ws_manager.py` | Backend |
| 11 | Ciclo 5m + ciclo 15m | `scheduler.py` | Backend |
| 12 | Interpretación IA velas | `ai_candles.py` | Backend |
| 13 | Reconciliación + Rate Limiter | `reconciliation.py` | Backend |
| 14 | Cleanup de datos | `data_cleanup.py` | Backend |
| 15 | Endpoint REST completo | `/api/etrade/*` | Full |
| 16 | Supabase schema (todas las tablas) | `schema.sql` | Full |
| 17 | Panel de Configuración completo | `pages/config.tsx` | Frontend |
| 18 | Ventana flotante Rule Engine | `components/RuleEngine.tsx` | Frontend |
| 19 | Dashboard principal (Realtime) | `pages/dashboard.tsx` | Frontend |
| 20 | Toggle Paper / Real (login) | `pages/login.tsx` | Frontend |
| 21 | Componente Fibonacci BB Panel | `components/FibBBPanel.tsx` | Frontend |
| 22 | Notificaciones Telegram | `telegram_notifier.py` | Backend |
| 23 | Backup / Restore configuración | `components/ConfigBackup.tsx` | Frontend |

### 15.2 Criterios de aceptación

```
FUNCIONALIDAD CORE:
  [ ] Pipeline completo ejecuta en < 3 segundos por símbolo
  [ ] 4 símbolos simultáneos sin degradación
  [ ] Régimen de mercado se clasifica correctamente cada 15m
  [ ] Rule Engine evalúa todas las condiciones Aa/Bb correctamente
  [ ] EMA20 phases usan percentiles adaptativos (no umbrales fijos)
  [ ] Basis multi-timeframe (15m, 4h, 1d) calcula confluence_score

GESTIÓN DE POSICIÓN:
  [ ] SL se recalcula sobre precio promedio ponderado tras cada entrada
  [ ] Break-even se activa correctamente en RR 1:1
  [ ] Cierre parcial proporcional: trades pequeños en upper_5, grande en upper_6
  [ ] Flujo 2 pasos: cierra siempre, abre solo si RR válido
  [ ] Modo defensivo (EMA50 < EMA200) cierra en upper_5/6 sin esperar Nivel 3

PROTECCIONES:
  [ ] Circuit breaker pausa sistema al superar pérdida diaria configurable
  [ ] Cooldown activo tras SL y TP
  [ ] Correlación > 0.80 bloquea entrada duplicada en misma dirección
  [ ] Precio de liquidación calculado y verificado vs SL antes de entrar
  [ ] Monitor de emergencia se dispara cuando ATR > promedio × multiplier

INFRAESTRUCTURA:
  [ ] WebSocket reconecta automáticamente si se cae la conexión
  [ ] Reconciliación detecta discrepancias bot vs Binance
  [ ] Rate limiter mantiene consumo bajo 50% del límite Binance
  [ ] Warm-up de 200 velas completo antes de activar señales
  [ ] Cleanup de datos ejecuta diariamente sin errores

FRONTEND:
  [ ] Toggle Paper/Real funciona en login
  [ ] Configuración persiste en Supabase y es editable
  [ ] Rule Engine: crear, editar, versionar y revertir reglas
  [ ] Dashboard se actualiza con Supabase Realtime (sin polling)
  [ ] IA candlestick muestra interpretación en modo Informativa

PAPER TRADING:
  [ ] Simula fills con precios reales de Binance
  [ ] Registra todos los trades en tabla paper_trades con rule_code
  [ ] P&L, SL, TP monitoreados igual que en modo real
  [ ] Telegram notifica con prefijo "[PAPER]"
```

---

## 16. HOJA DE RUTA SPRINTS 2 Y 3

```
SPRINT 2 — Calidad, análisis y optimización:
  ⬜ Backtesting module (datos históricos, misma lógica del pipeline)
  ⬜ Walk-forward testing (70% in-sample / 30% out-of-sample)
  ⬜ Dashboard de performance por regla (win rate Aa11, Aa22, etc.)
  ⬜ Rule Engine version control con comparación de performance
  ⬜ Modo Vinculante de IA candlestick (puede reducir sizing o vetar)
  ⬜ Optimización automática de parámetros por símbolo
  ⬜ Slippage tracking dashboard

SPRINT 3 — Expansión Forex:
  ⬜ DataProvider OANDA / Alpaca
  ⬜ Horarios de mercado Forex (24/5, Lun-Vie)
  ⬜ Swap rates overnight (equivalente a funding rate)
  ⬜ Misma lógica técnica, nuevos parámetros calibrados para Forex
  ⬜ Spread variable como costo integrado al RR

SPRINT 4+ — Opciones (documento separado cuando corresponda):
  ⬜ Modelo de opciones sobre subyacente (requiere documento propio)
```

---

*Documento v3 — eTrade Plataforma de Trading Algorítmico*
*Antigravity Dev Team — Marzo 2026*
*Versión 3.0 — Documento maestro Sprint 1 — Aprobado por Jhon (CEO)*
